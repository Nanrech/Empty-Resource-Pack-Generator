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

def download_version_manifest():
  response = requests.get(VERSION_MANIFEST_URL, allow_redirects=True, timeout=(10, 60))
  response.raise_for_status()

  with open(FILE_MANIFEST_JSON, "wb") as f:
    f.write(response.content)

def get_latest_versions_info():
  f = open(FILE_MANIFEST_JSON, "r")
  manifest_dict: dict = json.load(f)
  f.close()

  latest = manifest_dict.get("latest")
  if latest is None:
    raise ValueError("latest is missing from version manifest.")

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
    raise ValueError("versions is missing from version manifest.")

  for v in versions_iterable:
    v_id = v.get("id")
    if v_id == latest_versions_info["release"]["id"]:
      latest_versions_info["release"]["url"] = v.get("url")
    elif v_id == latest_versions_info["snapshot"]["id"]:
      latest_versions_info["snapshot"]["url"] = v.get("url")

  return latest_versions_info

def download_version_package(url):
  response = requests.get(url, allow_redirects=True, timeout=(10, 60))
  response.raise_for_status()

  with open(FILE_PACKAGE_JSON, "wb") as f:
    f.write(response.content)

def get_client_download_info():
  f = open(FILE_PACKAGE_JSON, "r")
  package_json = json.load(f)
  f.close()

  downloads = package_json.get("downloads")
  if downloads is None:
    raise ValueError("downloads is missing from version package.")

  client_info = downloads.get("client")
  if client_info is None:
    raise ValueError("Client download info is missing from version package.")
  return client_info.get("url"), client_info.get("sha1"), client_info.get("size")

def download_client_jar_as_zip(url, expected_sha1, expected_size):
  response = requests.get(url, allow_redirects=True, timeout=(10, 60))
  # fuck it we ball
  response.raise_for_status()
  content = response.content

  # compare size
  if expected_size is not None and len(content) != expected_size:
    raise ValueError(f"Client file size mismatch: expected {expected_size} bytes, received {len(content)}.")

  # compare hash
  if hashlib.sha1(content).hexdigest().lower() != expected_sha1.lower():
    raise ValueError("Client file SHA-1 checksum mismatch.")

  with open(FILE_CLIENT_JAR, "wb") as f:
    f.write(content)

def extract_client_zip():
  with zipfile.ZipFile(FILE_CLIENT_JAR, 'r') as z:
    required_files = ["version.json", "assets/minecraft/lang/en_us.json"]
    archive_files = z.namelist()

    for required_file in required_files:
      if required_file not in archive_files:
        raise zipfile.BadZipFile(f"Client JAR is missing {required_file}.")

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
    raise ValueError("version.json is malformed.")

  pack_info = version_json.get("pack_version")
  if not isinstance(pack_info, dict):
    raise ValueError("pack_version is missing or malformed in version.json.")

  if "resource_major" not in pack_info or "resource_minor" not in pack_info:
    raise ValueError("pack_version is missing resource_major or resource_minor.")

  # bc of the check before we can now assume these will work
  return {
    "major": pack_info["resource_major"],
    "minor": pack_info["resource_minor"],
  }

def rsp_mkdir_base_directory(path: Path):
  if path.exists():
    raise FileExistsError(f"Resource pack directory already exists: {path}")

  path.mkdir()

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
  out_name = PATH_OUTPUT_DIR / f"{name}.zip"
  if out_name.exists():
    raise FileExistsError(f"Resource pack ZIP already exists: {out_name}")

  with zipfile.ZipFile(out_name, "x", zipfile.ZIP_STORED) as zip_ref:
    for folder_name, _, filenames in os.walk(path):
      for filename in filenames:
        file_path = os.path.join(folder_name, filename)
        zip_ref.write(file_path, os.path.relpath(file_path, PATH_OUTPUT_DIR / name))

def _cleanup_temp_dir():
  if PATH_TEMP_DIR.exists():
    shutil.rmtree(PATH_TEMP_DIR)

def _cleanup_output_dir(name):
  output_path = PATH_OUTPUT_DIR / name
  if output_path.exists():
    shutil.rmtree(output_path)

def main():
  rsp_name = None
  rsp_created = False
  try:
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
      channel = "release" if RELEASE_OR_SNAPSHOT else "snapshot"
      raise ValueError(f"Latest {channel} info is missing from version manifest.")

    # Download version package and get target version info
    download_version_package(target_version_info["url"])
    target_url, target_sha1, target_size = get_client_download_info()
    if target_url is None:
      raise ValueError("Client download URL is missing.")
    if target_sha1 is None:
      raise ValueError("Client file SHA-1 is missing.")
    if target_size is None:
      raise ValueError("Client file size is missing.")

    # Download client.jar as zip and extract contents
    download_client_jar_as_zip(target_url, target_sha1, target_size)
    extract_client_zip()

    # Create new resourcepack dir
    rsp_name = FILENAME_RSP.replace("%", target_version_info["id"])
    rsp_path = PATH_OUTPUT_DIR / rsp_name
    rsp_mkdir_base_directory(rsp_path)
    rsp_created = True

    # Create pack.mcmeta and pack.png
    pack_info = get_version_pack_info()
    rsp_create_pack_mcmeta(rsp_path, pack_info)
    rsp_copy_pack_png(rsp_path)

    # Add the languages to the resourcepack
    lang_dir_path = rsp_create_assets_lang_dirs(rsp_path)
    rsp_make_lang_files(lang_dir_path)

    # Turn the resourcepack into a zip file
    rsp_pack_into_zip_file(rsp_path, rsp_name)
  finally:
    try:
      if rsp_created:
        _cleanup_output_dir(rsp_name)
    finally:
      _cleanup_temp_dir()

if __name__ == "__main__":
  main()
