import re
import sys
from pathlib import Path

source, target = sys.argv[1], sys.argv[2]
blocks = re.split(r"\n(?=[A-Za-z0-9])", Path(source).read_text(encoding="utf-8"))
kept = [block for block in blocks if not re.match(r"(nvidia-|triton|cuda-|pytest|psutil==|iniconfig==|pluggy==)", block)]
Path(target).write_text("\n".join(kept), encoding="utf-8")
