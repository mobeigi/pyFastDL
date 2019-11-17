#!/usr/bin/env python3

"""
    pyFastDL - FastDL syncer for SRCDS servers.
    Created by: mobeigi

    This program is free software: you can redistribute it and/or modify it under
    the terms of the GNU General Public License as published by the Free Software
    Foundation, either version 3 of the License, or (at your option) any later
    version.

    This program is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
    FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
    You should have received a copy of the GNU General Public License along with
    this program. If not, see <http://www.gnu.org/licenses/>.
"""

import os
from enum import IntEnum
import bz2
import shutil
import hashlib

# Globals
mod_rules_dict = {}
MIN_FILE_SIZE_TO_BZIP = 1048576
MAX_FILE_SIZE_TO_BZIP = 149999616

# Enums
class Mod(IntEnum):
    CSGO = 1

# Classes
class Server:
    def __init__(self, mod, server_path):
        self.mod = mod
        self.server_path = server_path

class FastDL:
    def __init__(self, mod, fastdl_path):
        self.mod = mod
        self.fastdl_path = fastdl_path

class ModRules:
    def __init__(self, mod, folder_rules):
        self.mod = mod
        self.folder_rules = folder_rules

class FolderRule:
    def __init__(self, path, extention_whitelist, expand_recursively=True):
        self.path = path
        self.extention_whitelist = extention_whitelist
        self.expand_recursively = expand_recursively

# Entry point
def main():
    # Populate mod data
    populate_mod_rules()

    # Set server folders 
    # TODO: add to config file
    test_server_1 = Server(Mod.CSGO, 'C:\\Games\\SteamDev\\pyFastDL Testing\\server1\\csgo')
    test_server_2 = Server(Mod.CSGO, 'C:\\Games\\SteamDev\\pyFastDL Testing\\server2\\csgo')
    test_fastdl = FastDL(Mod.CSGO, 'C:\\Games\\SteamDev\\pyFastDL Testing\\fastdl.example.com\\csgo')

    server_fastdl_mappings = {}
    server_fastdl_mappings.setdefault(test_fastdl, []).append(test_server_1)
    server_fastdl_mappings.setdefault(test_fastdl, []).append(test_server_2)

    # Loop over servers
    for fastdl, servers in server_fastdl_mappings.items():
        for server in servers:

            # Get mod rules
            mod_rules = mod_rules_dict[server.mod]

            for folder_rule in mod_rules.folder_rules:
                folder_path = server.server_path + folder_rule.path

                # Check that path exists
                if not os.path.isdir(folder_path) and not os.path.exists(folder_path):
                    print(f'Folder path dir "{folder_path}" does not exist')
                    continue

                # Iterate over files in folder
                if folder_rule.expand_recursively:
                    for root, subdirs, files in os.walk(folder_path):
                        for file in files:
                            source_file = root + os.sep + file

                            # Ensure checksum for this file is the same for all servers mapped to the same fastdl folder
                            # Otherwise, we have to fail as we don't know which file we should use
                            source_file_md5 = md5sum(source_file)

                            checksum_ok = True
                            for s in servers:
                                # Ignore current server
                                if s == server:
                                    continue
                                
                                test_source_file = s.server_path + folder_rule.path + os.sep + file
                                if os.path.exists(test_source_file) and os.path.isfile(test_source_file):
                                    test_source_file_md5 = md5sum(test_source_file)
                                    if test_source_file_md5 != source_file_md5:
                                        print(f'Error checksum mismatch for file "{source_file}" [MD5: {source_file_md5}] and "{test_source_file}" [MD5: {test_source_file_md5}].')
                                        checksum_ok = False

                            if not checksum_ok:
                                break

                            # Save source files modified time
                            source_file_mtime = os.path.getmtime(source_file)

                            # Check extension whitelist 
                            if any(file.endswith(ext) for ext in folder_rule.extention_whitelist):
                                # Check if file exists at target
                                target_path = fastdl.fastdl_path + folder_rule.path + remove_prefix(root, folder_path) + os.sep + file
                                target_path_bzipped = target_path + '.bz2'

                                # Only Compress files <= 150MB with bzip2, otherwise leave them raw
                                source_file_size = os.stat(source_file).st_size
                                dest_file = target_path_bzipped if MIN_FILE_SIZE_TO_BZIP < source_file_size < MAX_FILE_SIZE_TO_BZIP else target_path
                                
                                # If file exists, we should check if we need to update it
                                if os.path.exists(dest_file):
                                    # Compare target files timestamp with our timestamp
                                    dest_file_mtime = os.path.getmtime(dest_file)

                                    # Treat files with same modified time as identical (to avoid storing checksums/uncompressing to compare checksums etc)
                                    if source_file_mtime == dest_file_mtime:
                                        continue

                                # Delete old files if they exist (raw and/or compressed)
                                if os.path.exists(target_path_bzipped) and os.path.isfile(target_path_bzipped):
                                    os.remove(target_path_bzipped)
                                elif os.path.exists(target_path) and os.path.isfile(target_path):
                                    os.remove(target_path)

                                # Make required directories
                                os.makedirs(os.path.dirname(dest_file), exist_ok=True)

                                # At this point, we can update the file
                                if dest_file == target_path_bzipped:
                                    compressor = bz2.BZ2Compressor(9)

                                    f_source = open(source_file, 'rb')
                                    f_dest = open(dest_file, 'wb+')

                                    while True:
                                        data = f_source.read(1024)
                                        if not data:
                                            break
                                        cdata = compressor.compress(data)
                                        f_dest.write(cdata)

                                    f_dest.write(compressor.flush())
                                else:
                                    shutil.copyfile(source_file, dest_file)

                                # Copy over modified time
                                os.utime(dest_file, (source_file_mtime, source_file_mtime))
                        
                else:
                    root, subdirs, files = next(os.walk(folder_path))

    # Delete old files that no longer exist on any server as sourcefile
    for fastdl, servers in server_fastdl_mappings.items():
        # Get mod rules
        mod_rules = mod_rules_dict[Mod.CSGO]

        for folder_rule in mod_rules.folder_rules:
            folder_path = fastdl.fastdl_path + folder_rule.path

            # Check that path exists
            if not os.path.isdir(folder_path) and not os.path.exists(folder_path):
                print(f'Folder path dir "{folder_path}" does not exist')
                continue

            # Iterate over files in folder
            if folder_rule.expand_recursively:
                for root, subdirs, files in os.walk(folder_path):
                    for file in files:
                        fastdl_file = root + os.sep + file

                        file_uncompressed = file
                        if file_uncompressed.endswith('.bz2'):
                            file_uncompressed = file_uncompressed[:-4]
                        
                        file_exists_on_server = False

                        for server in servers:
                            test_source_file = server.server_path + folder_rule.path + os.sep + file_uncompressed
                            
                            if os.path.exists(test_source_file) and os.path.isfile(test_source_file):
                                file_exists_on_server = True

                        if not file_exists_on_server:
                            os.remove(fastdl_file)

def remove_prefix(text, prefix):
    return text[len(prefix):] if text.startswith(prefix) else text

# Source: https://stackoverflow.com/a/21565932/1800854
def md5sum(filename, blocksize=65536):
    hash = hashlib.md5()
    with open(filename, "rb") as f:
        for block in iter(lambda: f.read(blocksize), b""):
            hash.update(block)
    return hash.hexdigest()

# Populate static data
def populate_mod_rules():

    # CSGO
    folder_rules = []
    folder_rules.append(FolderRule(os.path.normpath('/maps'), ['.bsp', '.ain', '.nav', '.jpg', '.txt']))
    folder_rules.append(FolderRule(os.path.normpath('/materials'), ['.vtf', '.vmt', '.vbf', '.png', '.svg']))
    folder_rules.append(FolderRule(os.path.normpath('/models'), ['.vtx', '.vvd', '.mdl', '.phy', '.jpg', '.png']))
    folder_rules.append(FolderRule(os.path.normpath('/particles'), ['.pcf']))
    folder_rules.append(FolderRule(os.path.normpath('/sound'), ['.wav', '.mp3', '.ogg']))
    folder_rules.append(FolderRule(os.path.normpath('/resource/flash/econ'), ['.png']))
    folder_rules.append(FolderRule(os.path.normpath('/demo'), ['.dem']))
    csgo_rules = ModRules(Mod.CSGO, folder_rules)
    mod_rules_dict[Mod.CSGO] = csgo_rules

if __name__ == '__main__':
    main()