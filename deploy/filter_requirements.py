import re
import sys

blocks = re.split(r"\n(?=[A-Za-z0-9])", sys.stdin.read())
kept = [block for block in blocks if not re.match(r"(nvidia-|triton|cuda-|pytest|psutil==|iniconfig==|pluggy==)", block)]
sys.stdout.write("\n".join(kept))
