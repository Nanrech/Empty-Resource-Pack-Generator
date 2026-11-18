import requests
import json
import zipfile
import re
import shutil
import os
import hashlib

from pathlib import Path

# TODO: Make this a command line argument
RELEASE_OR_SNAPSHOT = False # True for stable, False for snapshot
VERSION_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
FILENAME_RSP         = "Empty Language Resource Pack (%)"

PATH_ROOT           = Path(".")
FILE_PACK_PNG       = PATH_ROOT / "pack.png"
PATH_TEMP_DIR       = PATH_ROOT / "temp"
PATH_OUTPUT_DIR     = PATH_ROOT / "output"
FILE_MANIFEST_JSON  = PATH_TEMP_DIR / "manifest.json"
FILE_PACKAGE_JSON   = PATH_TEMP_DIR / "package.json"
FILE_CLIENT_JAR     = PATH_TEMP_DIR / "client.zip"
FILE_CLIENT_VERSION = PATH_TEMP_DIR / "version.json"
FILE_EN_US          = PATH_TEMP_DIR / "en_us.json"


def create_temp_n_output_directories():
  PATH_TEMP_DIR.mkdir(exist_ok=True)
  PATH_OUTPUT_DIR.mkdir(exist_ok=True)

def _download_temp_stuff(url, file):
  r = requests.get(url, allow_redirects=True)
  with open(file, "wb") as f:
    f.write(r.content)

def download_version_manifest():
  _download_temp_stuff(VERSION_MANIFEST_URL, FILE_MANIFEST_JSON)

def get_latest_versions_info():
  f = open(FILE_MANIFEST_JSON, "r")
  manifest_dict: dict = json.load(f)
  f.close()

  latest = manifest_dict.get("latest")
  if latest is None:
    raise RuntimeError

  latest_versions_info = {
    "release": {
      "id": latest.get("release"),
      "url": ""
    },
    "snapshot": {
      "id": latest.get("snapshot"),
      "url": ""
    }
  }

  versions_iterable = manifest_dict.get("versions")
  if versions_iterable is None:
    raise RuntimeError

  for v in versions_iterable:
    v_id = v.get("id")
    if v_id == latest_versions_info["release"]["id"]:
      latest_versions_info["release"]["url"] = v.get("url")
    elif v_id == latest_versions_info["snapshot"]["id"]:
      latest_versions_info["snapshot"]["url"] = v.get("url")

  return latest_versions_info

def download_version_package(url):
  _download_temp_stuff(url, FILE_PACKAGE_JSON)

def get_client_download_info():
  f = open(FILE_PACKAGE_JSON, "r")
  package_json = json.load(f)
  f.close()

  downloads = package_json.get("downloads")
  if downloads is None:
    raise RuntimeError("placeholder")

  client_info = downloads["client"]
  return client_info.get("url"), client_info.get("sha1"), client_info.get("size")

def download_client_jar_as_zip(url, expected_sha1, expected_size):
  response = requests.get(url, allow_redirects=True, timeout=(10, 60))
  # fuck it we ball
  response.raise_for_status()
  content = response.content

  # compare size
  if expected_size is not None and len(content) != expected_size:
    raise RuntimeError("placeholder")

  # compare hash
  if hashlib.sha1(content).hexdigest().lower() != expected_sha1.lower():
    raise RuntimeError("Client download SHA-1 checksum mismatch.")

  with open(FILE_CLIENT_JAR, "wb") as f:
    f.write(content)

def extract_client_zip():
  with zipfile.ZipFile(FILE_CLIENT_JAR, 'r') as z:
    required_files = ["version.json", "assets/minecraft/lang/en_us.json"]
    archive_files = z.namelist()

    for required_file in required_files:
      if required_file not in archive_files:
        raise RuntimeError("placeholder")

    with z.open("version.json") as source:
      with open(FILE_CLIENT_VERSION, "wb") as destination:
        shutil.copyfileobj(source, destination)

    with z.open("assets/minecraft/lang/en_us.json") as source:
      with open(FILE_EN_US, "wb") as destination:
        shutil.copyfileobj(source, destination)

def get_version_pack_info():
  f = open(FILE_CLIENT_VERSION, "r", encoding="utf-8")
  version_json = json.load(f)
  f.close()

  if not isinstance(version_json, dict):
    raise RuntimeError("Couldn't open version.json. File is malformed or missing.")

  pack_info = version_json.get("pack_version")
  if pack_info is None:
    raise RuntimeError("pack_info is missing from version.json.")

  if "resource_major" not in pack_info or "resource_minor" not in pack_info:
    raise RuntimeError("pack_info is missing resource_major or resource_minor.")

  # bc of the check before we can now assume these will work
  return {
    "major": pack_info["resource_major"],
    "minor": pack_info["resource_minor"],
  }

# TODO: Warn if rsp already exists
def rsp_mkdir_base_directory(path: Path):
  path.mkdir(exist_ok=True)

def rsp_create_pack_mcmeta(path, info):
  major = info["major"]
  minor = info["minor"]

  pack_mcmeta = {
    "pack": {
      "description": "Change your language to English (Translation Keys)",
      "pack_format": major,
      "min_format": [major, minor],
      "max_format": [major, minor],
    },
    "language": {
      "en_usk": {
        "name": "English",
        "region": "Translation Keys",
        "bidirectional": False
      }
    }
  }

  # Unnecessary stuff that prevents lists from being indented
  output = json.dumps(pack_mcmeta, indent=2)
  output = re.sub(r"(?<=\[)[^\[\]]+(?=\])", lambda match : " ".join(match.group().split()), output)

  file_mcmeta = path / "pack.mcmeta"
  with open(file_mcmeta, "w") as f:
    f.write(output)

def rsp_copy_pack_png(path):
  shutil.copyfile(FILE_PACK_PNG, path / "pack.png")

def rsp_create_assets_lang_dirs(path):
  lang_dir_path: Path = path / "assets" / "minecraft" / "lang"
  lang_dir_path.mkdir(parents=True, exist_ok=True)
  return lang_dir_path

def _rsp_make_lang_en_us(path, en_us):
  with open(path / "en_us.json", "w", encoding="utf-8") as f:
    json.dump(en_us, f, indent=4)

def _rsp_make_lang_en_us_keys(path, en_us: dict):
  en_us_keys = {}
  for key in en_us.keys():
    en_us_keys[key] = key

  with open(path / "en_usk.json", "w", encoding="utf-8") as f:
    json.dump(en_us_keys, f, indent=4)

def rsp_make_lang_files(path):
  f = open(FILE_EN_US, "r", encoding="utf-8")
  en_us = json.load(f)
  f.close()

  _rsp_make_lang_en_us(path, en_us)
  _rsp_make_lang_en_us_keys(path, en_us)

def rsp_pack_into_zip_file(path, name):
  out_name = (PATH_OUTPUT_DIR / name).__str__() + ".zip"

  with zipfile.ZipFile(out_name, "w", zipfile.ZIP_STORED) as zip_ref:
    for folder_name, _, filenames in os.walk(path):
      for filename in filenames:
        file_path = os.path.join(folder_name, filename)
        zip_ref.write(file_path, os.path.relpath(file_path, PATH_OUTPUT_DIR / name))

def _cleanup_temp_dir():
  os.remove(PATH_TEMP_DIR / "client.zip")
  os.remove(PATH_TEMP_DIR / "en_us.json")
  os.remove(PATH_TEMP_DIR / "manifest.json")
  os.remove(PATH_TEMP_DIR / "package.json")
  os.remove(PATH_TEMP_DIR / "version.json")
  os.rmdir(PATH_TEMP_DIR)

def _cleanup_output_dir(name):
  shutil.rmtree(PATH_OUTPUT_DIR / name)

def cleanup_temp_n_output_directories(name):
  _cleanup_temp_dir()
  _cleanup_output_dir(name)

def main():
  # Prep
  # TODO: Command line arguments (release/snapshot, specify version, skip downloading, output as zip)
  # TODO: Add logging
  # TODO: Group up stuff into bigger functions of functions
  create_temp_n_output_directories()

  # Download version manifest
  download_version_manifest()
  latest_versions_info = get_latest_versions_info()

  target_version_info = None
  if RELEASE_OR_SNAPSHOT:
    target_version_info = latest_versions_info.get("release")
  else:
    target_version_info = latest_versions_info.get("snapshot")

  if target_version_info is None:
    raise RuntimeError

  # Download version package and get target version info
  download_version_package(target_version_info["url"])
  target_url, target_sha1, target_size = get_client_download_info()
  if None in [target_url, target_sha1, target_size]:
    raise RuntimeError("placeholder")

  # Download client.jar as zip and extract contents
  download_client_jar_as_zip(target_url, target_sha1, target_size)
  extract_client_zip()

  # Create new resourcepack dir
  rsp_name = FILENAME_RSP.replace("%", target_version_info["id"])
  rsp_path = PATH_OUTPUT_DIR / rsp_name
  rsp_mkdir_base_directory(rsp_path)

  # Create pack.mcmeta and pack.png
  pack_info = get_version_pack_info()
  rsp_create_pack_mcmeta(rsp_path, pack_info)
  rsp_copy_pack_png(rsp_path)

  # Add the languages to the resourcepack
  lang_dir_path = rsp_create_assets_lang_dirs(rsp_path)
  rsp_make_lang_files(lang_dir_path)

  # Turn the resourcepack into a zip file
  rsp_pack_into_zip_file(rsp_path, rsp_name)

  # Time to clean up this mess
  cleanup_temp_n_output_directories(rsp_name)

if __name__ == "__main__":
  main()
