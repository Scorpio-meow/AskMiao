import re
import sys

source, target = sys.argv[1], sys.argv[2]
blocks = re.split(r"\n(?=[A-Za-z0-9])", open(source, encoding="utf-8").read())
kept = [block for block in blocks if not re.match(r"(nvidia-|triton|cuda-)", block)]
open(target, "w", encoding="utf-8").write("\n".join(kept))
