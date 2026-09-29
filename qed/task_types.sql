-- TASK_TYPE 초기값. 작업 블록별 개별 부여, 공통 없음
INSERT OR IGNORE INTO task_type(name, ko, ok) VALUES
 ('mine','채광',1),('log','벌목',1),('farm','농사',1),('dig','삽질',1),('shear','가위사용',1),
 ('craft','제작(작업대)',1),('enchant','마법부여',0),
 ('furnace','화로',1),('blast_furnace','용광로',1),('smoker','훈연기',1),('campfire','모닥불',1),
 ('bucket','양동이',1),('fish','낚시',0),('hunt','사냥',1),('combat','전투',1),
 ('expedition','원정',1),('trade','거래',0),('store','정리(상자)',1),('rest','휴식',1),
 ('sleep','침대',1),('shelter','쉘터',1),('flee_pillar','도망(블럭)',1),('flee_run','도망(달리기)',1),
 ('eat','식사',1),('potion','포션사용',1),('melee','무기(근거리)',1),('ranged','무기(원거리)',0),
 ('elytra','비행(겉날개)',0),('boat','보트사용',1),('minecart','마인카트사용',1);
