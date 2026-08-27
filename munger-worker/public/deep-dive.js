(()=>{const css=document.createElement('style');css.textContent=`.dd-wrap{margin:18px 0}.dd-lecture{background:#fffdf8;border:1px solid #ddd2c2;border-radius:15px;margin:12px 0;overflow:hidden}.dd-lecture>summary{cursor:pointer;padding:16px 18px;font:700 18px Georgia,"Noto Serif KR",serif}.dd-body{border-top:1px solid #ddd2c2;padding:16px 18px}.dd-steps{display:grid;grid-template-columns:repeat(2,1fr);gap:9px}.dd-step{background:#f7f1e6;border-radius:11px;padding:12px}.dd-step b{display:block;color:#84392e;margin-bottom:4px}.atlas{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}.case{background:#fffdf8;border:1px solid #ddd2c2;border-radius:13px;padding:14px}.case .meta{font-size:11px;color:#84392e;font-weight:800}.case h3{margin:5px 0 8px}.case p{margin:5px 0}.case .why2{margin-top:9px;padding-top:8px;border-top:1px dashed #d7cab8;color:#5d554c}.psych-extra{display:block;margin-top:7px;padding-top:7px;border-top:1px dashed #ddd2c2;font-size:12px;color:#5f574f}.psych-extra b{color:#84392e}.lens{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.lens div{background:#f7f1e6;border:1px solid #ddd2c2;border-radius:12px;padding:11px}.lens b{display:block;color:#84392e}.micro{font-size:12px;color:#756e64}@media(max-width:820px){.dd-steps,.atlas,.lens{grid-template-columns:1fr}}`;document.head.appendChild(css);

const nav=document.querySelector('nav');if(nav){const a=document.createElement('a');a.href='#chapters';a.textContent='소챕터';nav.insertBefore(a,nav.querySelector('a[href="#themes"]'));const b=document.createElement('a');b.href='#cases';b.textContent='사례 해설';nav.insertBefore(b,nav.querySelector('a[href="#psych"]'));}

const lectures=document.querySelector('#lectures');if(lectures){const s=document.createElement('section');s.id='chapters';s.innerHTML=`<div class="kicker">CORE TALKS · CHAPTER LEVEL</div><h2>핵심 강연 5개 — 소챕터 단위 해설</h2><p class="muted">이 다섯 강연은 책의 사고법을 가장 직접적으로 구축한다. 아래는 ‘무슨 말을 했는가’보다 ‘논리가 어떤 순서로 전개되는가’를 따라간다.</p>
<details class="dd-lecture" open><summary>02강 · 세속적 지혜 — ‘격자틀’이 실제 기업 분석으로 내려오는 과정</summary><div class="dd-body"><div class="dd-steps">
<div class="dd-step"><b>1. 사실을 모형에 걸어라</b>낱개 지식은 쉽게 흩어진다. 직접 경험과 독서를 수학·공학·경제·심리 같은 핵심 모형의 격자에 걸어야 판단에 재사용할 수 있다.</div>
<div class="dd-step"><b>2. 규모는 하나의 힘이 아니다</b>경험곡선의 비용 절감, 기하학적 효율, 구매력, 전문화, 광고 접근성, 정보 신뢰가 서로 다른 경로로 규모의 이점을 만든다.</div>
<div class="dd-step"><b>3. P&G / TV 광고</b>비싼 TV 광고는 이미 대량 판매 기반이 있는 브랜드가 더 잘 감당한다. 규모가 광고를 가능하게 하고, 광고가 다시 브랜드와 판매량을 키우는 자기강화 구조다.</div>
<div class="dd-step"><b>4. 브랜드는 정보 비용을 낮춘다</b>소비자는 익숙한 제품을 선택함으로써 실패 위험과 탐색 비용을 줄인다. 브랜드의 경제적 가치는 단순한 ‘이미지’가 아니다.</div>
<div class="dd-step"><b>5. 인센티브는 행동 설계다</b>페덱스의 야간 분류 문제는 설득이나 압박이 아니라 보상 단위를 ‘시간’에서 ‘완료 물량’으로 바꾸자 해결됐다.</div>
<div class="dd-step"><b>6. 투자에서의 결론</b>좋은 기업을 찾을 때는 단일 해자를 찾기보다 여러 이점이 서로 강화되는지, 그 구조가 시간이 갈수록 강해지는지를 본다.</div>
</div><p class="why"><b>이 강연의 깊은 의미</b> · ‘복수 사고 모형’은 많이 아는 사람이 되라는 말이 아니다. 기업의 한 현상을 비용·심리·정보·경쟁·인센티브라는 여러 원인으로 동시에 설명할 수 있어야 한다는 뜻이다.</p></div></details>
<details class="dd-lecture"><summary>03강 · 후속편 — ‘지식’에서 ‘학습 시스템’으로</summary><div class="dd-body"><div class="dd-steps">
<div class="dd-step"><b>1. 정답보다 갱신 능력</b>버핏의 발전을 예로 들며, 한번 배운 투자법을 반복하는 것보다 새로운 현실에 맞춰 모형을 계속 수정하는 능력을 강조한다.</div>
<div class="dd-step"><b>2. 심리학이 빠지면 현실이 빠진다</b>사람이 바라는 것을 믿는 심리적 부인처럼, 실제 의사결정에 강한 현상이 교과서에서 충분히 통합되지 않았다고 비판한다.</div>
<div class="dd-step"><b>3. 체크리스트의 역할</b>여러 원칙과 심리적 힘을 한 번에 기억하기 어렵기 때문에, 주요 원칙을 체크리스트로 묶어 중요한 누락을 줄인다.</div>
<div class="dd-step"><b>4. 사우어크라우트 사례</b>괴혈병의 정확한 생화학적 원인을 몰라도 국가·선단 간 차이를 관찰하고 비교해 유용한 해법을 찾을 수 있다. 완벽한 이론보다 쓸 수 있는 지식이 먼저일 때가 있다.</div>
<div class="dd-step"><b>5. 현실을 직시하는 문화</b>좋은 조직은 이전 결론이 틀렸다는 사실을 인정할 수 있어야 한다. 지적 유연성은 개인뿐 아니라 조직문화의 문제다.</div>
<div class="dd-step"><b>6. 목표는 ‘안 틀리기’가 아니다</b>인간은 계속 틀린다. 중요한 것은 오류 빈도를 줄이고, 발견했을 때 더 빨리 수정하는 체계를 만드는 것이다.</div>
</div></div></details>
<details class="dd-lecture"><summary>04강 · 실용적 사고 — 코카콜라 사고실험을 단계별로</summary><div class="dd-body"><div class="dd-steps">
<div class="dd-step"><b>1. 먼저 문제를 수치화</b>1884년의 작은 자본을 훗날 거대한 기업 가치로 만들라는 목표를 놓고, 필요한 최종 규모부터 역산한다.</div>
<div class="dd-step"><b>2. 인버전</b>성공 조건뿐 아니라 브랜드 훼손, 경쟁제품, 소비 피로, 유통 실패처럼 목표를 망치는 조건을 먼저 찾는다.</div>
<div class="dd-step"><b>3. 생리적 보상</b>맛·향·질감·당·카페인·시원함처럼 반복 섭취를 강화하는 직접 보상 요소를 설계한다.</div>
<div class="dd-step"><b>4. 조건화와 연상</b>파블로프식 조건화로 음료를 즐거움·활력·사회적 장면과 연결하고, 제품 자체 이상의 심리적 가치를 만든다.</div>
<div class="dd-step"><b>5. 사회적 증거</b>사람들이 남들이 마시는 것을 보고 따라 마시게 되면 판매량이 다시 인지된 매력도를 높이는 피드백이 생긴다.</div>
<div class="dd-step"><b>6. 롤라팔루자</b>맛 하나가 아니라 보상·조건화·브랜드·사회적 증거·광고·유통이 같은 방향으로 결합할 때 비선형적 결과가 나온다.</div>
</div><p class="why"><b>왜 코카콜라인가</b> · 멍거는 완성된 기업을 사후적으로 칭찬하려는 게 아니라, 다학문적 모델을 실제 ‘설계 문제’에 넣으면 어떤 순서로 사고할 수 있는지를 시연한다.</p></div></details>
<details class="dd-lecture"><summary>09강 · 강단 경제학 — ‘유용한 단순화’와 ‘가짜 정확성’의 경계</summary><div class="dd-body"><div class="dd-steps">
<div class="dd-step"><b>1. 경제학의 강점 인정</b>희소성·기회비용·비교우위·규모 같은 기본 개념은 현실에서 매우 강력하다.</div>
<div class="dd-step"><b>2. 문제는 학문적 관할권</b>현실 문제는 심리·생물·공학·법·경제가 섞여 있는데, 학문은 자신의 경계 밖 설명을 충분히 가져오지 않는 경향이 있다.</div>
<div class="dd-step"><b>3. 물리학 선망</b>복잡한 사회 시스템에서도 물리학처럼 정밀하고 안정적인 방정식을 만들 수 있다고 착각하면 모델의 불확실성을 숨기게 된다.</div>
<div class="dd-step"><b>4. 워싱턴포스트</b>효율적 시장 이론을 지나치게 믿으면, 눈앞에 보이는 극단적 저평가조차 이론에 맞춰 무시할 수 있다.</div>
<div class="dd-step"><b>5. 기술 ≠ 투자수익</b>생산성을 높이는 신기술이 경쟁 때문에 소비자에게 혜택을 넘기면, 산업 발전과 자본 소유자의 수익은 달라질 수 있다.</div>
<div class="dd-step"><b>6. 해법</b>최대한 단순화하되 현실의 핵심 변수를 지울 정도로 단순화하지 않는다. 숫자의 정밀함과 사고의 정확성을 구분한다.</div>
</div></div></details>
<details class="dd-lecture"><summary>11강 · 인간적 오판 — 25개 목록보다 더 중요한 ‘상호작용’</summary><div class="dd-body"><div class="dd-steps">
<div class="dd-step"><b>1. 경향은 대부분 유용하다</b>사회적 증거, 권위 추종, 일관성 같은 경향은 보통 빠른 협력과 판단을 돕는다. 그래서 제거할 대상이 아니다.</div>
<div class="dd-step"><b>2. 환경이 경향을 오작동시킨다</b>불확실성·강한 감정·스트레스·손실 위협이 커지면 평소 유용한 휴리스틱이 과도하게 작동할 수 있다.</div>
<div class="dd-step"><b>3. 사회적 증거는 ‘행동’뿐 아니라 ‘무행동’도 전파한다</b>서피코, 목격자 방관, 이사회 침묵의 공통점은 다른 사람의 침묵이 ‘문제없다’는 증거처럼 작동한다는 것이다.</div>
<div class="dd-step"><b>4. 스트레스는 다른 편향을 증폭한다</b>책은 강한 스트레스가 사고 기능을 저하시킬 뿐 아니라 사회적 증거 같은 경향도 더 강하게 만들 수 있다고 설명한다.</div>
<div class="dd-step"><b>5. 밀그램을 단일 편향으로 보지 않는다</b>권위만이 아니라 일관성, 사회적 맥락, 점진적 에스컬레이션 등이 함께 작동하는 복합 현상으로 읽는다.</div>
<div class="dd-step"><b>6. 대응은 ‘편향 이름 외우기’가 아니다</b>체크리스트, 반증, 독립적 검토, 인센티브 재설계, 시간 지연처럼 판단 환경을 바꾸는 절차가 핵심이다.</div>
</div><p class="why"><b>11강의 진짜 결론</b> · 멍거가 원하는 것은 심리학 시험을 잘 보는 사람이 아니라, ‘내가 지금 어떤 힘에 밀리고 있는지’ 점검하고 의사결정 환경을 바꿀 수 있는 사람이다.</p></div></details>`;
lectures.insertAdjacentElement('afterend',s);}

const themes=document.querySelector('#themes');if(themes){const c=document.createElement('section');c.id='cases';const cases=[
['02강','P&G와 TV 광고','대규모 판매 기반이 비싼 TV 광고를 감당하게 하고, 광고가 다시 브랜드와 판매를 강화한다.','규모의 경제가 비용 절감 하나가 아니라 광고 접근성과 브랜드 정보효과까지 포함한다는 사례.'],
['02강','FedEx 야간 분류','시간 기준 급여 대신 처리 물량과 조기 퇴근을 연결하자 지연 문제가 빠르게 해결된다.','사람을 설득하기 전에 인센티브 구조를 보라는 메시지.'],
['03강','사우어크라우트와 괴혈병','정확한 비타민 지식 없이도 네덜란드 선원과 영국 선원의 차이를 관찰해 실용적 해법을 찾는다.','완벽한 이론이 없어도 비교·관찰·실험으로 쓸 수 있는 지식을 만들 수 있음을 보여준다.'],
['04강','코카콜라 사고실험','맛·당·카페인·조건화·사회적 증거·광고·유통을 한 방향으로 결합한다.','롤라팔루자가 추상 개념이 아니라 사업 설계의 실제 도구임을 시연한다.'],
['06강','기관투자 마찰비용','전문가와 거래·자문이 늘수록 시장 전체 수익에서 최종 투자자에게 남는 몫은 줄 수 있다.','운용사에게 합리적인 행동과 자금 소유자에게 합리적인 행동을 분리한다.'],
['07강','주가와 부의 효과','주가 상승이 소비를 늘리고, 소비가 다시 이익과 주가에 영향을 주는 순환을 설명한다.','복잡계는 원인 하나로 떨어지는 물리학적 퍼즐이 아니라 피드백 시스템이라는 점을 보여준다.'],
['08강','퀸트 테크','좋은 기업이 잘못된 스톡옵션 회계와 보상 유인, 점진적 정당화로 무너진다.','대형 사기를 개인의 악함보다 인센티브·회계·사회적 증거의 결합으로 본다.'],
['09강','워싱턴포스트 자사주','극단적 저평가 상황에서도 효율적 시장 이론에 매달리면 명백한 경제적 기회를 놓칠 수 있다.','좋은 이론도 현실의 반증 앞에서는 수정되어야 한다.'],
['09강','신형 방직기','기술 생산성 향상이 경쟁을 통해 소비자에게 이전되면 기업주 수익은 크게 좋아지지 않을 수 있다.','산업의 발전과 투자자의 수익률을 구분한다.'],
['10강','학습하는 기계','오랜 성공 뒤에도 이전 10년의 기술이 다음 10년에 그대로 통한다고 보지 않는다.','평생 학습은 지식 축적이 아니라 변화에 맞춰 사고모형을 갱신하는 습관이다.'],
['11강','서피코','부패한 조직에서 다른 사람의 동조와 침묵이 부패를 정상으로 보이게 만든다.','인센티브와 사회적 증거가 결합하면 개인의 도덕성만으로 버티기 어려워진다.'],
['11강','엘리베이터 실험','주변 사람들이 모두 같은 방향을 보면 개인도 무의식적으로 따라간다.','사회적 증거가 얼마나 자동적인지 보여주는 작은 실험.'],
['11강','이사회 무행동','다른 이사들이 반대하지 않는다는 사실 자체가 ‘문제없다’는 신호로 작동한다.','집단에서 행동뿐 아니라 무행동도 전염될 수 있다는 경고.'],
['11강','밀그램','권위자의 지시 아래 평범한 사람이 극단적 행동까지 갈 수 있다.','멍거는 이를 권위 하나가 아니라 여러 심리적 힘의 복합작용으로 읽는다.'],
['11강','맥도널 더글러스 비상탈출 테스트','시험 실패의 손실이 커질수록 박탈 과잉 반응 등 여러 심리적 압력이 판단을 왜곡한다.','현실의 큰 사고는 단일 편향보다 복합 압력의 결과이므로 체크리스트가 필요하다는 사례.']
];c.innerHTML=`<div class="kicker">CASE ATLAS</div><h2>책의 사례 아틀라스 — ‘왜 이 사례가 여기 있는가’</h2><p class="muted">멍거의 사례는 재미를 위한 일화가 아니라 사고모형을 기억시키는 장치다. 사건보다 그 사례가 증명하려는 구조를 읽는다.</p><div class="atlas">${cases.map(x=>`<article class="case"><span class="meta">${x[0]}</span><h3>${x[1]}</h3><p>${x[2]}</p><p class="why2"><b>왜 넣었나</b> · ${x[3]}</p></article>`).join('')}</div>`;themes.insertAdjacentElement('afterend',c);}

const psych=document.querySelectorAll('#psych .psych>div');const extra=[
['경고','보상 기준이 바뀌었을 때 주장까지 같이 바뀌는가?','대응','사람보다 먼저 보상식을 적어본다.'],
['경고','좋아하는 사람의 데이터만 관대하게 해석하는가?','대응','사람 이름을 가리고 사실만 재검토한다.'],
['경고','싫어하는 대상의 장점을 자동으로 지우는가?','대응','반대편의 최선 논거를 강제로 작성한다.'],
['경고','불확실성이 불편해서 너무 빨리 결론내리는가?','대응','결정 시한과 미해결 질문을 분리한다.'],
['경고','이미 말한 입장을 지키기 위해 새 증거를 무시하는가?','대응','철회 조건을 사전에 적는다.'],
['경고','질문이 줄고 익숙한 설명만 반복되는가?','대응','왜?를 한 단계 더 묻는다.'],
['경고','공정성 감정이 경제적 사실 판단을 덮는가?','대응','규범 판단과 결과 예측을 분리한다.'],
['경고','절대 성과보다 남의 성과 때문에 판단이 흔들리는가?','대응','비교 기준을 사전에 고정한다.'],
['경고','받은 호의나 적대 때문에 사실 판단이 달라지는가?','대응','관계와 의사결정을 분리한다.'],
['경고','좋은/나쁜 이미지가 무관한 속성에 번지는가?','대응','연상과 인과를 따로 적는다.'],
['경고','고통스러운 사실만 특별히 믿기 어려워지는가?','대응','불편한 사실을 먼저 요약한다.'],
['경고','내 선택·내 소유·내 능력을 과대평가하는가?','대응','외부 기준과 베이스레이트를 본다.'],
['경고','원하는 시나리오의 확률을 높게 잡는가?','대응','실패 시나리오를 먼저 수치화한다.'],
['경고','손실 회복 욕구가 추가 위험을 정당화하는가?','대응','과거 원가를 버리고 현재 기대값만 본다.'],
['경고','남들이 한다는 사실이 근거의 대부분인가?','대응','군중 정보 없이도 같은 결론인지 묻는다.'],
['경고','절대 가격보다 비교 대상 때문에 싸 보이는가?','대응','독립 가치 기준을 다시 계산한다.'],
['경고','압박이 커질수록 사고가 단순·극단화되는가?','대응','중대 결정은 가능하면 스트레스 피크를 피한다.'],
['경고','쉽게 떠오르는 사건을 실제 빈도처럼 느끼는가?','대응','체크리스트와 외부 통계를 사용한다.'],
['경고','오래 안 쓴 기술을 여전히 잘한다고 가정하는가?','대응','핵심 기술을 반복 훈련한다.'],
['경고','물질 의존이 현실 해석과 자기통제를 바꾸는가?','대응','판단능력을 훼손하는 환경 자체를 제거한다.'],
['경고','과거 전문성이 새로운 문제에도 그대로 통한다고 보는가?','대응','새 학습 속도와 한계를 인정한다.'],
['경고','직급·명성 때문에 질문을 멈추는가?','대응','권위와 근거를 분리해 검토한다.'],
['경고','말과 회의가 많아졌는데 정보가 늘지 않는가?','대응','핵심 질문과 결정사항만 남긴다.'],
['경고','이유가 있다는 사실만으로 설득되는가?','대응','그 이유가 실제 인과인지 검증한다.'],
['경고','여러 압력이 동시에 한 방향으로 작용하는가?','대응','각 힘을 따로 적고 상호작용을 점검한다.']
];psych.forEach((el,i)=>{if(extra[i])el.insertAdjacentHTML('beforeend',`<span class="psych-extra"><b>${extra[i][0]}</b> · ${extra[i][1]}<br><b>${extra[i][2]}</b> · ${extra[i][3]}</span>`);});

const thesis=document.querySelector('#thesis');if(thesis){const lens=document.createElement('div');lens.className='dd-wrap';lens.innerHTML=`<h3>이 책을 읽을 때 쓰는 4개 렌즈</h3><div class="lens"><div><b>원인 렌즈</b>이 결과를 만든 힘은 하나인가, 여러 개인가?</div><div><b>인센티브 렌즈</b>누가 무엇을 하면 보상을 받는가?</div><div><b>심리 렌즈</b>누가 무엇을 믿고 싶어 하는가?</div><div><b>인버전 렌즈</b>이 판단이 크게 실패하는 경로는 무엇인가?</div></div>`;thesis.appendChild(lens);}
})();