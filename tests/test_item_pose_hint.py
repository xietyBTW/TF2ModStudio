"""Подсказка позы оружия в кадре: камера иконки, кость руки или ничего"""

from src.services import item_pose_hint
from src.services.item_pose_hint import HAND_FRAME, pose_hint, worn_on_player

SMD = """version 1
nodes
0 "{bone}" -1
end
skeleton
time 0
0 0 0 0 0 0 0
end
triangles
mat
0 0 0 0 0 0 1 0 0
0 1 0 0 0 0 1 0 0
0 0 1 0 0 0 1 0 0
end
"""


def _model(tmp_path, bone="weapon_bone", attachment=""):
    (tmp_path / "w.smd").write_text(SMD.format(bone=bone), encoding="utf-8")
    qc = tmp_path / "w.qc"
    qc.write_text(f'$modelname "w.mdl"\n$body "w" "w.smd"\n{attachment}\n', encoding="utf-8")
    item_pose_hint.pose_hint.cache_clear()
    item_pose_hint.worn_on_player.cache_clear()
    return str(qc)


def test_icon_camera_axes_in_obj_space(tmp_path):
    # Камера без поворота: стоит перед моделью и смотрит в +X Source, left =
    # +Y, up = +Z. В OBJ (x, z, -y): view (1,0,0), forward (0,0,-1), up (0,1,0)
    qc = _model(tmp_path, attachment='$attachment "icon_camera" "weapon_bone" -10 0 0 rotate 0 0 0')
    hint = pose_hint(qc)
    assert [round(v, 6) for v in hint["view"]] == [1, 0, 0]
    assert [round(v, 6) for v in hint["forward"]] == [0, 0, -1]
    assert [round(v, 6) for v in hint["up"]] == [0, 1, 0]


def test_hand_bone_without_camera_gets_hand_frame(tmp_path):
    assert pose_hint(_model(tmp_path)) == HAND_FRAME


def test_world_prop_is_left_alone(tmp_path):
    """Аптечка или реквизит стоят как в мире - их не кладём"""
    assert pose_hint(_model(tmp_path, bone="medkit")) is None


def test_missing_qc_is_none(tmp_path):
    item_pose_hint.pose_hint.cache_clear()
    assert pose_hint(str(tmp_path / "nope.qc")) is None


def test_camera_looking_away_is_ignored(tmp_path):
    """Помсон: icon_camera в модели смотрит мимо неё - иконку снимали не ею,
    и стороны берутся от руки"""
    qc = _model(tmp_path, attachment='$attachment "icon_camera" "weapon_bone" 10 0 0 rotate 0 0 0')
    assert pose_hint(qc) == HAND_FRAME


def test_back_item_is_worn_on_player(tmp_path):
    """Ранец знамени: кости игрока, ни руки, ни камеры иконки - его надевают"""
    assert worn_on_player(_model(tmp_path, bone="bip_spine_3")) is True
    assert pose_hint(_model(tmp_path, bone="bip_spine_3")) is None


def test_held_or_iconed_item_is_not_worn(tmp_path):
    assert worn_on_player(_model(tmp_path)) is False
    shield = '$attachment "icon_camera" "bip_spine_3" -10 0 0 rotate 0 0 0'
    assert worn_on_player(_model(tmp_path, bone="bip_spine_3", attachment=shield)) is False
    assert worn_on_player(_model(tmp_path, bone="medkit")) is False
