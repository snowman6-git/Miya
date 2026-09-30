"""0.3 판단 교사 규칙 자체검사: python data/test_judge.py"""
import gen as G

F = G.FAIL
assert G.fail_label("stuck", 1, 0, 1, 0, 0, 20, False, True) == F[0]  # 일시 실패 → 재시도
assert G.fail_label("stuck", 3, 0, 3, 0, 0, 20, False, True) == F[2]  # 같은 사유 3연속 → 도움 (루프 차단)
assert G.fail_label("no_target", 1, 3, 1, 0, 0, 20, False, False) == F[3]  # 원정 반복 실패 + 혼자 → 포기
assert G.fail_label("no_tool", 1, 0, 1, 0, 0, 20, False, True) == F[1]
assert G.recover_label(5000, 40, 30, "lava", False, 0, "hand") == G.RECOVER[1]  # 용암 = 템 소멸
assert G.recover_label(0.3, 10, 10, "zombie", False, 0, "hand") == G.RECOVER[1]  # 흙 하나
assert G.recover_label(500, 40, 30, "zombie", True, 0, "hand") == G.RECOVER[0]  # 다이아 = 밤이라도
assert G.qty_label("drop", "아카시아 나무 버려", "acacia_log", 8, False) == "전부"  # 싼 템
assert G.qty_label("give", "다이아 줘", "diamond", 30, False) == "되묻기"
assert G.qty_label("give", "다이아 다 줘", "diamond", 30, False) == "전부"
assert G.qty_label("craft", "횃불 64개 되게 만들어", "torch", 10, True) == "말한 개수 맞추기(총)"
assert G.pick_label("drop", "acacia_log", ["oak_log", "birch_log"], {"oak_log": 8, "birch_log": 3}) == 2  # 미보유 종 → 되묻기
assert G.pick_label("drop", "acacia_log", ["oak_log", "acacia_log"], {"oak_log": 8, "acacia_log": 3}) == 1
assert G.food_label({"golden_apple": 1, "bread": 5}, 6, 10, True) == "golden_apple"
assert G.food_label({"golden_apple": 1, "bread": 5}, 18, 10, False) == "bread"
assert G.food_label({"rotten_flesh": 5, "apple": 1}, 18, 10, False) == "apple"
assert G.weapon_label({"hand": 100, "iron_sword": 80}, True, "creeper", 1) == "iron_sword+shield"
assert G.target_label([("zombie", 3), ("creeper", 4)]) == 1
assert G.hunt_label([("horse", 5, 2)]) == 1  # 고기 없는 동물만 → 원정
print("ok")
