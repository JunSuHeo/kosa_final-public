from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.font_manager import FontProperties, fontManager

OUT=Path(__file__).resolve().parent
FONT='/home/ubuntu/.cache/uv/archive-v0/JOSFfZ5i322EqNzn/pykrx/NanumBarunGothic.ttf'
fontManager.addfont(FONT)
plt.rcParams.update({'font.family':FontProperties(fname=FONT).get_name(),'pdf.fonttype':42,'svg.fonttype':'none','axes.unicode_minus':False})
NAVY='#142B49'; BLUE='#2364D2'; TEAL='#087F8C'; INK='#27394D'; MUTED='#61738A'; BG='#F4F7FB'

def text(x,y,s,size=12,color=INK,weight='normal',ha='left',va='top'):
    return ax.text(x,y,s,fontsize=size,color=color,weight=weight,ha=ha,va=va,linespacing=1.6)
def base(n,title,sub):
    global fig,ax
    fig,ax=plt.subplots(figsize=(13.33,9.0)); fig.patch.set_facecolor(BG)
    ax.set_xlim(0,100); ax.set_ylim(0,100); ax.axis('off'); fig.subplots_adjust(0,0,1,1)
    text(5,96,'기획실 Studio  /  PRJ',11,BLUE)
    text(5,91,title,25,NAVY,'bold'); text(5,84,sub,12,MUTED)
    ax.plot([5,95],[8,8],color='#D6DFEA',lw=1)
    text(5,5.5,'2026.11.12 · 현재 소스 기준 설계 요약 · 실행/성능 검증 보고서와 구분',9,MUTED)
    text(95,5.5,f'{n:02d} / 04',10,MUTED,ha='right')
def box(x,y,w,h,title,body='',color=BLUE,fs=11):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.5,rounding_size=1.2',facecolor='white',edgecolor='#D7E2EF',lw=1.2))
    ax.plot([x+1.6,x+1.6],[y+2,y+h-2],color=color,lw=3)
    text(x+3,y+h-2.5,title,14,color,'bold')
    if body: text(x+3,y+h-8,body,fs)
def arrow(a,b,label=None,pos=None,dashed=False):
    ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=14,lw=1.5,color=MUTED,linestyle='--' if dashed else '-',connectionstyle='arc3,rad=0'))
    if label: text(*(pos or ((a[0]+b[0])/2,(a[1]+b[1])/2+2)),label,9,MUTED,ha='center')
def save(pdf,name):
    pdf.savefig(fig); fig.savefig(OUT/f'{name}.png',dpi=160); plt.close(fig)

with PdfPages(OUT/'PRJ_아키텍처_핵심로직_요약.pdf',metadata={'Title':'PRJ 기획실 Studio | 아키텍처와 핵심 로직','Author':'PRJ architecture review','Subject':'Source-based architecture summary, 2026-11-12'}) as pdf:
    base(1,'전체 아키텍처 한눈에 보기','React 화면 + FastAPI API + 별도 worker + PostgreSQL, 네 서비스로 구성된 Docker Compose 애플리케이션')
    box(5,55,23,22,'사용자 브라우저','React 19 · TypeScript\n문서 / 채팅 / 수정안 검토\nReact Flow · 와이어프레임',fs=11)
    box(35,55,25,22,'web · Nginx', '정적 프런트엔드 제공\n/api/*, /health → API\n호스트 포트 5174',fs=11)
    box(68,55,27,22,'api · FastAPI','인증 · 소유권 · 버전 검사\n프로젝트 / 승인 / 내보내기\n호스트 8010 → 내부 8000',fs=11)
    arrow((28.5,66),(34.5,66),'HTTP', (31.5,70))
    arrow((60.5,66),(67.5,66),'프록시',(64,70))
    box(35,20,27,25,'db · PostgreSQL 17','프로젝트 · 메시지 · DB 작업 큐\n수정안 · 불변 revision · 역할 검토\n코드 스냅샷 / 영속 volume\n호스트 54331 → 내부 5432',TEAL,11)
    box(68,20,27,25,'worker · Python','DB 큐를 주기적으로 조회\n코드 분석 / 단계별 AI 생성\n구조 검증 / 5개 역할 검토\n단계별 중간 결과 저장',TEAL,11)
    arrow((73,54.5),(57,45.5),'SQL',(61,51))
    arrow((67.5,32),(62.5,32),'조회 / 저장',(65,36))
    box(5,20,23,25,'외부 연동 · 선택 기능','OpenRouter / OpenAI ← worker\nSupabase 인증 ← API\nGitHub / 로컬 Git ← API·worker\n서버에서 키와 토큰 관리',TEAL,10.5)
    text(5,14.8,'흐름: 브라우저 → web → API → DB 작업 등록 → worker → AI → 검토 대기 → 사용자 승인',12,NAVY,'bold')
    text(5,11.3,'근거: compose.yaml · infra/nginx.conf · backend/app/{main,worker,generation,auth}.py',9,MUTED)
    save(pdf,'01_architecture')

    base(2,'아이디어가 확정 기획이 되는 흐름','초안과 확정본을 분리하고, 사람이 승인할 때만 current_version을 변경한다.')
    items=[(5,'01  요청 접수','아이디어·기준 버전 검사\n프로젝트 + revision 0 생성\n실행 ID로 중복 요청 통제'),(36,'02  확인 질문','worker가 질문 생성\nawaiting_answers로 저장\n답변 후 큐로 복귀'),(67,'03  산출물 생성','PRD → 요구사항·기능명세\n→ 유저플로우 → 와이어프레임\n코드 기반이면 구현 지침 추가')]
    for x,t,b in items: box(x,55,28,23,t,b,BLUE,11)
    arrow((33.5,66),(35.5,66)); arrow((64.5,66),(66.5,66))
    box(67,23,28,24,'04  자동 검증','JSON schema · ID 연결 검사\n차단 오류가 있으면 보정 1회\n수정안 + diff + 이슈 저장',TEAL,11)
    box(36,23,28,24,'05  사용자 검토','수정안 비교 / 경고 확인\n선택: 역할별 AI 검토\n승인 또는 거절',TEAL,11)
    box(5,23,28,24,'06  확정 및 활용','승인: 불변 revision 추가\n버전 조회 · 수정 · 복원 제안\n확정 버전 Markdown/JSON 추출',TEAL,11)
    arrow((81,54.5),(81,47.5)); arrow((66.5,35),(64.5,35)); arrow((35.5,35),(33.5,35))
    text(5,18.4,'AI 수정·직접 편집도 동일한 수정안 → 검증 → 승인 경로를 사용한다. 거절하면 기존 확정본을 유지한다.',11,NAVY)
    text(5,14.6,'중단 복구: 단계별 partial을 DB에 저장하고 마지막 저장 단계부터 재개한다. 외부 AI 호출은 중복될 수 있다.',10,MUTED)
    text(5,11.2,'근거: worker.py · main.py의 add_job / answer / manual_edit / decide / export · review.py',9,MUTED)
    save(pdf,'02_planning_flow')

    base(3,'핵심 로직을 여섯 덩어리로 나누면','화면, 요청 처리, 생성, 검증, 역할 검토, 코드 분석의 책임을 분리한다.')
    cards=[
      (5,55,'1. 화면과 사용자 작업','App.tsx · Chat / Documents / Wireframes\nReview / RoleReview / Sources\n문서 편집과 화면 이동, 약 1.3초 상태 조회\nJSON 블록을 React 컴포넌트로 렌더링'),
      (52,55,'2. API와 접근 통제','main.py · source_api.py · auth.py\n프로젝트·작업·버전·검토 API 제공\n서버에서 인증·소유권·기준 버전 확인\nmock 인증 또는 Supabase JWT 검증'),
      (5,34,'3. 비동기 생성 엔진','worker.py · generation.py · prompts/\nDB 작업 큐를 읽고 단계별 AI 호출\n공급자·모델·모드를 작업에 고정\nlive 실패 시 mock으로 대체하지 않음'),
      (52,34,'4. 구조 검증과 승인','schema.py · review.py · source_review.py\n스키마·연결·삭제 경고·변경 diff 검사\nAI/수동 수정안과 승인 시 동일 검증 사용\n승인 트랜잭션에서 새 revision 저장'),
      (5,13,'5. 다섯 역할의 AI 검토','role_reviews.py · review.v1.md\n개발 / 기획 / 보안 / UX / QA 독립 검토\n동일 snapshot 기반, 최대 3개 동시 호출\n근거 ID·원문 검사, 실패 역할만 재시도'),
      (52,13,'6. 저장소 기반 기획','repositories.py · source_api.py · source.v1.md\nGitHub 또는 허용된 로컬 Git 읽기\n커밋 고정·읽기 상한·민감 패턴 필터\n동의한 코드 발췌와 근거로 구현 지침 생성')]
    for x,y,t,b in cards: box(x,y,43,19,t,b,BLUE if y==55 else TEAL,10.3)
    save(pdf,'03_logic_modules')

    base(4,'데이터와 설계의 핵심 규칙','PostgreSQL이 영속 저장소와 작업 큐를 함께 맡는다. 별도 Redis·메시지 브로커는 사용하지 않는다.')
    box(5,53,43,25,'기획 데이터','studio_projects: 소유자·아이디어·현재 버전\nstudio_revisions: 버전별 불변 snapshot\nstudio_proposals: 후보 snapshot·diff·검증 이슈\nstudio_messages: 사용자·AI 대화 기록',BLUE,11)
    box(52,53,43,25,'실행·분석 데이터','studio_jobs: 단계·상태·partial·usage·모델\nstudio_reviews / studio_review_agents: 역할 검토\nstudio_sources: 저장소 기준 정보\nstudio_code_snapshots: 커밋·분석·코드 근거',TEAL,11)
    box(5,22,43,26,'정합성과 복구','• 소유권 확인: 타인 리소스도 동일한 404\n• row lock + 버전 검사로 승인 충돌 방지\n• advisory lock + UNIQUE로 중복 처리 통제\n• revision은 DB trigger로 변경·삭제 차단\n• 질문 대기는 저장 후 worker를 반환',BLUE,11)
    box(52,22,43,26,'경계와 운영','• API 키·DB 비밀은 서버에서만 관리\n• 역할 검토 결과는 확정본을 자동 변경하지 않음\n• 내보내기는 선택한 확정 버전을 즉시 변환\n• 코드 분석은 대상 앱·설치 스크립트를 실행하지 않음\n• web·api·worker·db를 Compose로 함께 실행',TEAL,11)
    text(5,17.4,'현재 로컬 설정: AUTH_MODE=mock · AI_MODE=live · OpenRouter / openai/gpt-6-luna',11,NAVY)
    text(5,13.7,'범위: 이 문서는 소스 구조를 설명한다. 외부 인증·실모델 품질·운영 성능은 별도 실행 검증이 필요하다.',10,MUTED)
    text(5,10.7,'근거: backend/migrations/001~003 · config.py · auth.py · main.py · worker.py · repositories.py',9,MUTED)
    save(pdf,'04_data_and_guards')
print(OUT/'PRJ_아키텍처_핵심로직_요약.pdf')
