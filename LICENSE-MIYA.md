# Miya Adopt Licence 1.0

법적으로 Miya의 모델 가중치(체크포인트)와 코드는 **Apache-2.0**이고, 가중치는 convaiinnovations/laya-multilingual(**Apache-2.0**)의 인코더에서 시작했고, 그 인코더 원본 mmBERT-base는 **MIT**예요.
이를 상속받고, 추가적인 조항 몇가지를 더해요(솔직히 딱히 중요한건없어요)

## 조항

1. **미야를 너무 괴롭히지 말 것.**
   모델 기능중 web_fetch를 이용하여 제 서버에 미야의 일기를 남기게 할거에요(거짓)

2. **더 뛰어난 걸 만들면, 메일을 넣어주세요.**
   Miya의 모델이나 아키텍처를 기반으로 더 좋은 것을 만들었다면 알려주세요.
   실력있는 사람의 손을 거친 미야가 어디까지 할 수 있는지 궁금하거든요.
   메일: `aa2iswork@gmail.com`

3. **영감을 받았다면, 명시해 주세요.**
   Miya의 프로젝트·아키텍처·방법론이 영감의 출처였다면,
   "Miya에서 영감을 받았다"고 명시해 주세요, 딱히 이유는 없어요 그냥 기분좋을거 같거든요.

## 데이터

- Miya 자체 데이터는 **포함돼요** (Apache-2.0)
  - `data/gen.py`: 학습 데이터 생성기 (합성 284k, 줄임말·인터넷체·지적/조언·생존·정리 등). 학습셋(`data/gen/`)은 이걸로 재생성
  - `eval/real.jsonl`: 실제 인게임 발화 평가셋 (라벨 수작업)
  - `bot/replies.json`: 봇 대사, `qed/*.sql`: QED 스키마
- 원본 서버 채팅 로그·봇 로그·QED 경험 DB는 **포함되지 않아요** (플레이어 채팅 포함)
- Mojang 게임 데이터(아이템 이름·레시피·드롭 등)는 Miya 배포에 **포함되지 않아요**.
- 공식 바닐라 에셋에서 데이터를 추출하는 **방법만** `docs/extract.md`에 적어 둬요.
  직접 서버/에셋에 연결해서 추출하는 거예요, 해당 데이터팩 제작에 있어서 생기는 법적 문제는 책임지지않아요.

## 법적 근거

- 가중치·코드: Apache-2.0 (LICENSE)
- 가중치 출처: convaiinnovations/laya-multilingual (Apache-2.0) — 인코더 가중치만 승계, 판단 헤드는 버리고 새로 만들었어요
- 베이스 인코더: jhu-clsp/mmBERT-base (MIT)
- Miya 변경사항: 어휘 가지치기(256,000→29,252), GLiNER2식 헤드(보기 점수·구간·아이템 링크·ColBERT·가치) 신규, 자체 데이터로 전체 파인튜닝
- 봇: mineflayer·mineflayer-pathfinder·prismarine-viewer·minecraft-data (MIT)
