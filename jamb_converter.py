from index_model import IndexSet

TABLE = {
    0: "0",
    1: "+1",
    2: "+2",
    3: "+3",
    4: "+4",
    5: "-3",
    6: "-2",
    7: "-1",
}


def convert_indices(indices):

    result = IndexSet()

    # 1. 64ギアの範囲（0〜63）に正規化して昇順にソート
    # これにより、0（64）が自動的に先頭（最小値）へ配置されます
    sorted_normalized = sorted([idx % 64 for idx in indices])

    # 2. 0表記を 64 表記に統一して格納
    result.original = [64 if idx == 0 else idx for idx in sorted_normalized]

    # 3. ソートされた順序と完全に同期させて Jamb Peg 表記へ変換
    for idx in result.original:
        if idx == 64:
            result.jamb.append("0")
        else:
            result.jamb.append(TABLE[idx % 8])

    return result