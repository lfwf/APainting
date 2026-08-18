from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np


def px(p, w, h):
    return (int(round(p[0] / 1000 * (w - 1))), int(round(p[1] / 1000 * (h - 1))))


def poly(mask, value, pts, w, h):
    arr = np.array([px(p, w, h) for p in pts], np.int32)
    cv2.fillPoly(mask, [arr], int(value))


def line(mask, value, pts, w, h, thick_n=90):
    arr = np.array([px(p, w, h) for p in pts], np.int32)
    thick = max(3, int(round(thick_n / 1000 * min(w, h))))
    cv2.polylines(mask, [arr], False, int(value), thickness=thick, lineType=cv2.LINE_8)


def ellipse(mask, value, center, axes, w, h):
    c = px(center, w, h)
    ax = max(2, int(round(axes[0] / 1000 * w)))
    ay = max(2, int(round(axes[1] / 1000 * h)))
    cv2.ellipse(mask, c, (ax, ay), 0, 0, 360, int(value), -1)


def save_preview(mask: np.ndarray, out: Path, labels: dict[int, str]):
    palette = {
        0: (248, 246, 240),
        1: (238, 107, 86),
        2: (78, 144, 216),
        3: (217, 168, 61),
        4: (103, 175, 102),
        5: (48, 177, 169),
        6: (146, 104, 204),
        7: (225, 111, 167),
        8: (111, 159, 82),
    }
    rgb = np.zeros((*mask.shape, 3), np.uint8)
    for value in np.unique(mask):
        rgb[mask == value] = palette.get(int(value), (160, 160, 160))
    cv2.imwrite(str(out), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def riverscape(run: Path):
    src = cv2.imread(str(run / 'assets/source.png'))
    h, w = src.shape[:2]
    m = np.zeros((h, w), np.uint8)

    # 2 river corridor first; semantic foreground units overwrite it below.
    poly(m, 2, [(160,570),(360,570),(490,585),(610,570),(760,600),(900,650),(940,760),
                (850,900),(650,940),(420,935),(170,910),(40,820),(50,680)], w, h)

    # 4 left bank flora/rocks, irregular bank-side area.
    poly(m, 4, [(0,320),(180,320),(300,390),(380,470),(455,590),(430,660),(350,690),
                (250,665),(160,705),(0,705)], w, h)

    # 5 right iris/tall-flora bank.
    poly(m, 5, [(500,350),(1000,340),(1000,750),(900,760),(820,725),(730,705),(650,660),
                (590,590),(545,500)], w, h)

    # 7 lower-right foreground flora.
    poly(m, 7, [(625,700),(1000,665),(1000,1000),(610,1000),(625,910),(690,850)], w, h)

    # 6 water lilies and pads.
    poly(m, 6, [(20,720),(125,690),(250,700),(390,730),(430,815),(330,850),(175,850),(40,820)], w, h)

    # 3 stepping stones; explicit local shapes, not a rectangle.
    for c, a in [
        ((600,625),(70,22)), ((560,655),(72,22)), ((475,690),(75,23)), ((555,730),(90,28)),
        ((620,770),(105,30)), ((565,815),(115,34)), ((500,865),(125,32))
    ]:
        ellipse(m, 3, c, a, w, h)

    # 1 upper flowering branch: a semantic silhouette region. It is intersected with
    # actual foreground support below, so it becomes an object-like mask rather than a box.
    poly(m, 1, [(0,0),(1000,0),(1000,455),(900,400),(820,350),(740,315),(670,300),
                (620,470),(455,470),(400,370),(310,350),(220,335),(100,300),(0,300)], w, h)

    # Keep semantic labels only near actual line/accent pixels. This turns coarse AI
    # regions into a thin object-support map and prevents large empty areas from acting
    # like implicit bounding boxes.
    line_mask = cv2.imread(str(run/'analysis/line_mask.png'), 0) > 0
    accent_mask = cv2.imread(str(run/'analysis/accent_mask.png'), 0) > 0
    support = (line_mask | accent_mask).astype(np.uint8)
    support = cv2.dilate(support, np.ones((13,13), np.uint8), iterations=1) > 0
    m[~support] = 0

    line_mask = cv2.imread(str(run/'analysis/line_mask.png'), 0) > 0
    accent_mask = cv2.imread(str(run/'analysis/accent_mask.png'), 0) > 0
    support = (line_mask | accent_mask).astype(np.uint8)
    support = cv2.dilate(support, np.ones((13,13), np.uint8), iterations=1) > 0
    m[~support] = 0

    out = run / 'analysis/unit_map.png'
    cv2.imwrite(str(out), m)
    save_preview(m, run / 'analysis/unit_map_authored_preview.png', {})

    plan = {
      'coordinate_space':'normalized_1000','style':'botanical_single_line_stationery',
      'strategy':'scaffold_then_local_completion','unit_map_path':'analysis/unit_map.png',
      'units':[
        {'id':'upper_flowering_branch','label':'upper flowering branch','kind':'upper_branch','root':{'x':985,'y':415},'direction':'along_structure','grammar':'branch_growth','priority':0,'layer':0,'subdivide':True,'mask_value':1,'token_ids':[],'notes':'AI-authored semantic mask corridor; no bbox ownership'},
        {'id':'river_spine','label':'river corridor and water flow','kind':'river','root':{'x':520,'y':570},'direction':'far_to_near','grammar':'river_flow','priority':1,'layer':0,'subdivide':True,'mask_value':2,'token_ids':[],'notes':'semantic water corridor'},
        {'id':'stepping_stones','label':'stepping stones','kind':'stone_cluster','root':{'x':570,'y':620},'direction':'far_to_near','grammar':'stone_contour','priority':2,'layer':1,'subdivide':True,'mask_value':3,'token_ids':[],'notes':'individual stone masks'},
        {'id':'left_bank_flora','label':'left bank flora and rocks','kind':'flora_cluster','root':{'x':120,'y':690},'direction':'bottom_up','grammar':'botanical_growth','priority':3,'layer':1,'subdivide':True,'mask_value':4,'token_ids':[],'notes':'left organic bank unit'},
        {'id':'right_bank_irises','label':'right bank irises and tall plants','kind':'flora_cluster','root':{'x':810,'y':710},'direction':'bottom_up','grammar':'botanical_growth','priority':4,'layer':1,'subdivide':True,'mask_value':5,'token_ids':[],'notes':'right iris unit'},
        {'id':'water_lilies','label':'water lilies and pads','kind':'water_lily_cluster','root':{'x':170,'y':790},'direction':'center_out','grammar':'contour_first','priority':5,'layer':2,'subdivide':True,'mask_value':6,'token_ids':[],'notes':'lily local unit'},
        {'id':'lower_right_flora','label':'lower-right foreground flora','kind':'flora_cluster','root':{'x':820,'y':930},'direction':'bottom_up','grammar':'botanical_growth','priority':6,'layer':2,'subdivide':True,'mask_value':7,'token_ids':[],'notes':'foreground flora unit'}
      ],
      'dependencies':[{'before':'river_spine','after':'stepping_stones','reason':'water scaffold before stones'}],
      'rationale':'Semantic indexed map authored from visual subject understanding; rectangles are not used for path ownership.'
    }
    (run/'scene_plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')


def mountain(run: Path):
    src = cv2.imread(str(run / 'assets/source.png'))
    h, w = src.shape[:2]
    m = np.zeros((h, w), np.uint8)

    # Background mountain semantic mass.
    poly(m, 1, [(120,180),(500,165),(1000,205),(1000,500),(780,500),(620,480),(500,500),
                (350,500),(180,470)], w, h)

    # River corridor.
    poly(m, 2, [(430,470),(600,470),(650,540),(590,610),(530,690),(500,760),(580,830),
                (650,900),(500,925),(330,900),(280,840),(340,760),(390,680),(410,590)], w, h)

    # Bank/rock masses before plants overwrite them.
    poly(m, 5, [(0,420),(360,420),(470,520),(460,700),(420,825),(300,870),(0,850)], w, h)
    poly(m, 6, [(585,430),(1000,420),(1000,900),(610,900),(570,790),(590,650)], w, h)

    # Left pines: narrow triangular semantic silhouettes, not rectangular ranges.
    poly(m, 3, [(155,175),(115,235),(75,315),(20,455),(285,455),(225,315),(190,235)], w, h)
    poly(m, 3, [(250,285),(215,330),(170,405),(145,485),(350,485),(320,405),(285,330)], w, h)
    poly(m, 3, [(325,355),(295,400),(250,505),(405,505),(370,405),(350,375)], w, h)
    line(m, 3, [(155,175),(155,470)], w, h, 32)
    line(m, 3, [(250,285),(250,485)], w, h, 28)
    line(m, 3, [(325,355),(325,505)], w, h, 25)

    # Right pines.
    poly(m, 4, [(745,345),(710,390),(655,535),(830,535),(790,395)], w, h)
    poly(m, 4, [(855,295),(810,350),(735,550),(970,550),(910,350)], w, h)
    line(m, 4, [(745,345),(745,535)], w, h, 28)
    line(m, 4, [(855,295),(855,545)], w, h, 32)

    # Foreground flora represented as multiple organic vertical corridors/flower groups.
    # left
    for pts, th in [
        ([(90,850),(90,690),(80,560),(75,505)],75),
        ([(155,850),(150,690),(165,585),(180,530)],90),
        ([(220,850),(215,700),(220,610),(230,565)],95),
        ([(285,850),(280,710),(285,625),(300,585)],85),
        ([(340,850),(340,735),(360,650)],70),
    ]:
        line(m, 7, pts, w, h, th)
    for c,a in [((175,610),(65,48)),((215,590),(75,55)),((275,590),(70,55))]:
        ellipse(m,7,c,a,w,h)

    # right
    for pts, th in [
        ([(650,865),(650,735),(660,640)],85),
        ([(720,865),(720,690),(720,590)],105),
        ([(790,865),(790,710),(810,620)],105),
        ([(860,865),(855,700),(880,610)],95),
        ([(930,860),(925,720),(930,570)],80),
    ]:
        line(m, 8, pts, w, h, th)
    for c,a in [((705,600),(75,50)),((875,650),(80,55))]:
        ellipse(m,8,c,a,w,h)

    line_mask = cv2.imread(str(run/'analysis/line_mask.png'), 0) > 0
    accent_mask = cv2.imread(str(run/'analysis/accent_mask.png'), 0) > 0
    support = (line_mask | accent_mask).astype(np.uint8)
    support = cv2.dilate(support, np.ones((13,13), np.uint8), iterations=1) > 0
    m[~support] = 0

    out = run / 'analysis/unit_map.png'
    cv2.imwrite(str(out), m)
    save_preview(m, run / 'analysis/unit_map_authored_preview.png', {})

    plan = {
      'coordinate_space':'normalized_1000','style':'botanical_single_line_stationery',
      'strategy':'scaffold_then_local_completion','unit_map_path':'analysis/unit_map.png',
      'units':[
        {'id':'mountain_mass','label':'distant mountain mass','kind':'mountain_mass','root':{'x':500,'y':185},'direction':'center_out','grammar':'mountain_contour','priority':0,'layer':0,'subdivide':True,'mask_value':1,'token_ids':[],'notes':'AI semantic mountain mask; pines explicitly excluded/overwritten'},
        {'id':'river_spine','label':'river through valley','kind':'river','root':{'x':520,'y':485},'direction':'far_to_near','grammar':'river_flow','priority':1,'layer':0,'subdivide':True,'mask_value':2,'token_ids':[],'notes':'river semantic corridor'},
        {'id':'left_pines','label':'left pine cluster','kind':'tree_cluster','root':{'x':175,'y':500},'direction':'bottom_up','grammar':'tree_growth','priority':2,'layer':1,'subdivide':True,'mask_value':3,'token_ids':[],'notes':'tree silhouettes overwrite mountain where overlapping'},
        {'id':'right_pines','label':'right pine cluster','kind':'tree_cluster','root':{'x':815,'y':515},'direction':'bottom_up','grammar':'tree_growth','priority':3,'layer':1,'subdivide':True,'mask_value':4,'token_ids':[],'notes':'tree silhouettes overwrite mountain where overlapping'},
        {'id':'left_bank_rocks','label':'left bank rocks','kind':'stone_cluster','root':{'x':260,'y':760},'direction':'far_to_near','grammar':'stone_contour','priority':4,'layer':1,'subdivide':True,'mask_value':5,'token_ids':[],'notes':'left bank geometry'},
        {'id':'right_bank_rocks','label':'right bank rocks','kind':'stone_cluster','root':{'x':780,'y':835},'direction':'far_to_near','grammar':'stone_contour','priority':5,'layer':1,'subdivide':True,'mask_value':6,'token_ids':[],'notes':'right bank geometry'},
        {'id':'left_foreground_flora','label':'left foreground flora','kind':'flora_cluster','root':{'x':180,'y':835},'direction':'bottom_up','grammar':'botanical_growth','priority':6,'layer':2,'subdivide':True,'mask_value':7,'token_ids':[],'notes':'organic plant corridors'},
        {'id':'right_foreground_flora','label':'right foreground flora','kind':'flora_cluster','root':{'x':760,'y':850},'direction':'bottom_up','grammar':'botanical_growth','priority':7,'layer':2,'subdivide':True,'mask_value':8,'token_ids':[],'notes':'organic plant corridors'}
      ],
      'dependencies':[{'before':'mountain_mass','after':'left_pines','reason':'background before foreground trees'},{'before':'mountain_mass','after':'right_pines','reason':'background before foreground trees'}],
      'rationale':'Semantic indexed map authored from visual subject understanding; rectangles are not used for path ownership.'
    }
    (run/'scene_plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__ == '__main__':
    root = Path('/mnt/data/apainting_v2_test')
    riverscape(root/'riverscape')
    mountain(root/'mountain')
