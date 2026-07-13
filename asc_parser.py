import re
from diagram_model import Diagram
from facet_model import Facet
from jamb_converter import convert_indices

def load_asc(filename):
    diagram = Diagram()
    diagram.author = ""
    diagram.ri = "1.54"
    diagram.index_gear = 64
    diagram.instructions = []

    with open(filename, "r", encoding="latin-1") as f:
        content = f.read()

    # 継続行結合
    content = re.sub(r'\r?\n[ \t]+', ' ', content)
    lines = content.split('\n')

    facet_id = 1
    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith("H"):
            if "Designed by" in line or "Author" in line or ";" in line:
                author_part = line[1:].replace("Designed by", "").strip()
                if diagram.author:
                    diagram.author += " " + author_part
                else:
                    diagram.author = author_part
        elif line.startswith("I"):
            parts = line.split()
            if len(parts) > 1:
                diagram.ri = parts[1]
        elif line.startswith("g"):
            parts = line.split()
            if len(parts) > 1:
                try:
                    diagram.index_gear = abs(int(parts[1]))
                except ValueError:
                    pass
            continue

        if not line.startswith("a"):
            continue

        parts = line.split()
        if len(parts) < 3:
            continue

        try:
            angle = float(parts[1])
            distance = float(parts[2])
        except ValueError:
            continue

        raw_indices = []
        name = ""
        instruction_parts = []
        
        EXPECT_INDEX = 0
        EXPECT_NAME = 1
        INSTRUCTION = 2
        
        state = EXPECT_INDEX
        
        for p in parts[3:]:
            if state == EXPECT_INDEX:
                if p == "n":
                    state = EXPECT_NAME
                else:
                    try:
                        val = float(p)
                        raw_indices.append(val)
                    except ValueError:
                        state = INSTRUCTION
                        instruction_parts.append(p)
            elif state == EXPECT_NAME:
                if not name:
                    name = p
                state = EXPECT_INDEX
            elif state == INSTRUCTION:
                instruction_parts.append(p)
        
        instruction = " ".join(instruction_parts).strip()

        facet = Facet()
        facet.id = facet_id
        facet.angle = angle
        facet.distance = distance
        facet.raw_indices = raw_indices
        
        rounded_indices = [int(round(x)) for x in raw_indices]
        facet.index = convert_indices(rounded_indices)
        
        facet.name = name if name else ""
        facet.has_name = bool(name)
        facet.instruction = instruction
        
        diagram.facets.append(facet)
        facet_id += 1

    # ★修正箇所: 名前に惑わされず、純粋に「角度」で表の振り分けを行う
    p_count, c_count, g_count = 1, 1, 1
    
    for facet in diagram.facets:
        upper = facet.name.upper() if facet.name else ""
        
        # 1. 角度が0ならTable
        if abs(facet.angle) < 1e-3 or upper == "TABLE" or upper == "T":
            facet.section = "Table"
            if not facet.name: facet.name = "T"
            
        # 2. 角度が90度 (89.9度以上) ならGirdle
        elif abs(facet.angle) > 89.9:
            facet.section = "Girdle"
            if not facet.name: 
                facet.name = f"G{g_count}"
                g_count += 1
                
        # 3. 角度がプラスなら Crown (上部)
        elif facet.angle > 0:
            facet.section = "Crown"
            if not facet.name:
                facet.name = f"C{c_count}"
                c_count += 1
                
        # 4. 角度がマイナスなら Pavilion (下部)
        else:
            facet.section = "Pavilion"
            if not facet.name:
                facet.name = f"P{p_count}"
                p_count += 1

    return diagram