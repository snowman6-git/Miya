-- QED(Quasi-Evolutionary Diary) 경험 DB 스키마 (SQLite). 실제 생성은 model/serve.py 시작시 (create if not exists)
-- goals: GOAL 1회 = 요청·목표·방법(via)·성공·소요ms·실패사유·ctx·vars(도구티어·장비·시간 등 조건)
-- steps: GOAL 의 스텝별 도구·ms·성공 / deaths: 사망 원인·가해자·인벤 가치·회복 판단 / placed: 설치물 좌표
-- 데이터(data/qed.db)는 배포 안함
CREATE TABLE deaths(id integer primary key, ts real, goal_id int, req text, cause text, killer text, hp int, food int, night int,
  armor int, weapon text, pos text, dim text, inv text, inv_value real, vars text, recover text, fix text);
CREATE TABLE goals(id integer primary key, ts real, req text, goal text, cnt int, via text, ok int, ms int, fail text, ctx text, vars text);
CREATE TABLE placed(kind text, x int, y int, z int, ts real, primary key(x, y, z));
CREATE TABLE steps(goal_id int, i int, type text, target text, cnt int, tool text, ms int, ok int, fail text);
CREATE INDEX g_via on goals(goal, via);
