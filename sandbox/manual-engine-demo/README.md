# 수동 엔진용 테스트 프로젝트

두 정수를 더하는 작은 CLI다. 최종 프로젝트의 루트는 `PRJ/`이며, 현재 `workflow/config/projects/prj.json`은 테스트를 위해 이 데모만 대상으로 삼는다. 제품 PRJ 파일은 변경하지 않는다.

저장소 루트에서 현재 프로그램과 테스트를 확인할 수 있다.

```bash
python3 -B sandbox/manual-engine-demo/src/calculator.py 3 5
python3 -B -m unittest discover -s sandbox/manual-engine-demo/tests/unit -v
python3 -B -m unittest discover -s sandbox/manual-engine-demo/tests/e2e -v
```

설정의 테스트 `cwd`는 각각 `sandbox/manual-engine-demo/tests/unit`, `sandbox/manual-engine-demo/tests/e2e`다. 해당 디렉터리에서는 `python3 -B -m unittest discover -s . -v`를 실행한다. 코드·테스트·문서 디렉터리만 허용 범위에 넣으므로 프로젝트 루트에서 실행하는 명령과 설정의 실행 디렉터리를 구분한다. 외부 패키지와 테스트용 인증정보는 필요 없다.

수정 허용 범위는 `src/`, `tests/`, `specs/`다. 작업 지침 `AGENTS.md`는 읽기 전용 컨텍스트이며 README는 자동 수정 범위에 포함하지 않는다.

WSL에 설치한 Codex CLI `0.169.0`과 공식 권장 테스트 모델 `gpt-6.1-sol`을 `prj.json`에 명시했다. 설정은 `ready`지만 이는 구조·경로·명시된 실행 선택이 준비됐다는 뜻이다. 계정 로그인, 모델 이용 권한과 실제 작업 호출은 별도 확인이 필요하다. 모델 선택 근거는 https://learn.chatgpt.com/docs/models 이다.

첫 실제 실행 전 WSL에서 `codex login`으로 로그인한다. 인증정보를 설정 파일이나 작업 요청에 넣지 않는다. 설치 후 CLI를 업데이트하면 설정의 고정 버전과 달라져 차단되므로, 사용 버전을 확인하고 설정도 검토해야 한다.

```bash
python3 -B workflow/runtime/validate_config.py workflow/config/projects/prj.json --repo-root .
python3 -B -m workflow.runtime.run --config workflow/config/projects/prj.json --task "계산기에 --operation subtract 선택지를 추가해 줘. 옵션을 생략하면 더하기를 유지하고 설계문서와 Unit/E2E 테스트도 갱신해 줘."
```

현재 엔진은 후보 변경을 저장소 밖의 실행 결과 디렉터리에 보관한다. `result.json`의 `workspace_path`에서 결과를 확인해야 하며, 원본 데모에 변경이 자동 반영되지는 않는다. GitHub Issue·Actions 수동 버튼은 이번 테스트 프로젝트 설정의 범위에 포함되지 않는다.
