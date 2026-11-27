"""Read XYZ files while preserving the optional empty comment line."""
from pathlib import Path
import math

def parse_xyz(path):
    lines=Path(path).read_text().splitlines()
    natoms=int(lines[0].strip())
    atom_lines=lines[2:2+natoms]
    if len(atom_lines)!=natoms or any(x.strip() for x in lines[2+natoms:]):
        raise ValueError("unexpected XYZ frame length")
    atoms=[]
    for row in atom_lines:
        el,x,y,z,*_=row.split()
        coords=tuple(map(float,(x,y,z)))
        if not all(math.isfinite(v) for v in coords):
            raise ValueError("non-finite Cartesian coordinate")
        atoms.append((el.capitalize(),*coords))
    return atoms
