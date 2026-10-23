"""Collect installed dependency license texts without copying user configuration."""
from importlib.metadata import distributions
from pathlib import Path
import shutil
import sys

root=Path('build/third-party-licenses');root.mkdir(parents=True,exist_ok=True)
for dist in distributions():
    for file in dist.files or ():
        if 'license' not in file.name.lower() and 'copying' not in file.name.lower() and 'notice' not in file.name.lower():continue
        source=Path(dist.locate_file(file))
        if source.is_file() and source.suffix.lower() in ('','.txt','.md','.rst'):
            target=root/dist.metadata['Name']/str(file).replace('/','_').replace('\\','_')
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
for source in (Path(sys.base_prefix)/'LICENSE.txt',Path(sys.base_prefix)/'LICENSE'):
    if source.exists():shutil.copyfile(source,root/'Python-LICENSE.txt')
