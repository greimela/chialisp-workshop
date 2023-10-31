import os
from pathlib import Path

from clvm_tools_rs import compile_clvm


def build(file: str) -> bool:
    project_path = Path.cwd()
    include_path = project_path.joinpath("clsp/include")
    clvm_files = []
    for path in Path(project_path).rglob(file):
        if path.is_dir():
            for clvm_path in Path(path).rglob("*.cl[vs][mp]"):
                clvm_files.append(clvm_path)
        else:
            clvm_files.append(path)

    for filename in clvm_files:
        hex_file_name: str = filename.name + ".hex"
        full_hex_file_name = Path(filename.parent).joinpath(hex_file_name)
        # We only rebuild the file if the .hex is older
        if not (full_hex_file_name.exists() and full_hex_file_name.stat().st_mtime > filename.stat().st_mtime):
            outfile = str(filename) + ".hex"
            try:
                print("Beginning compilation of " + filename.name + "...")
                compile_clvm(str(filename), outfile, search_paths=[os.fspath(include_path)])
                print("...Compilation finished")
                return True
            except Exception as e:
                print("Couldn't build " + filename.name + ": " + str(e))
                return False

        return True
