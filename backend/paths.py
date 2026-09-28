#!/usr/bin/env python3
"""NUL paths for Borg; any traversal error makes archive creation fail."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import config,selected,read
if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit("Expected the runner-generated scope configuration")
    c=read(Path(sys.argv[1]))
    for rel in selected(Path.cwd(),c):sys.stdout.buffer.write(os.fsencode(rel)+b'\0')
