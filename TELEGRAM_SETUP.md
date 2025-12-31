# 텔레그램 알림 설정을 위한 GitHub Secrets 등록 가이드

텔레그램 알림이 오지 않는다면, 99%의 확률로 GitHub 저장소에 "열쇠(Secret)"가 없기 때문입니다.
아래 순서대로 따라해주시면 해결됩니다.

## 1단계: 깃허브 설정 페이지 이동
1. 현재 보고 계신 GitHub 저장소(Repo) 상단 메뉴에서 **[Settings]** 탭을 클릭하세요.
2. 왼쪽 사이드바 메뉴에서 **[Secrets and variables]** 를 찾아서 클릭하세요.
3. 하위 메뉴가 열리면 **[Actions]** 를 클릭하세요.

## 2단계: 시크릿(Secret) 키 등록
화면 중앙 우측에 있는 초록색 버튼 **[New repository secret]** 을 클릭하여 아래 두 가지를 각각 등록해야 합니다.

### 첫 번째 시크릿 등록
- **Name**: `TELEGRAM_BOT_TOKEN`
- **Secret**: (사용자의 봇 토큰 값을 붙여넣기하세요)
  - *예: `123456789:ABCdefGHIjklMNOpqrSTUvwxYZ`*
- 입력 후 **[Add secret]** 버튼 클릭.

### 두 번째 시크릿 등록
다시 **[New repository secret]** 버튼을 누르세요.
- **Name**: `TELEGRAM_CHAT_ID`
- **Secret**: (사용자의 채팅 ID 값을 붙여넣기하세요)
  - *예: `12345678`*
- 입력 후 **[Add secret]** 버튼 클릭.

## 3단계: 확인 및 재실행
1. 두 개의 시크릿(`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`)이 목록에 보이면 성공입니다.
2. 이제 **[Actions]** 탭으로 이동하세요.
3. 왼쪽에서 **[Daily AI News]** 워크플로우를 선택하세요.
4. **[Run workflow]** 버튼을 눌러 수동으로 뉴스를 생성해보세요.
5. 잠시 후 텔레그램 메시지가 도착하는지 확인하세요.

---
**참고**: 텔레그램 봇에게 말을 먼저 걸어두어야 메시지를 받을 수 있습니다. 봇과의 채팅방에서 `/start`를 치거나 아무 메시지나 보내두세요.
