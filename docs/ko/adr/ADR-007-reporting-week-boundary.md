---
id: ADR-007
title: 보고 주간 경계: ISO Week, Thu 13:00 KST, UTC 저장
status: Accepted
date: 2026-06-04
---

# ADR-007: 보고 주간 경계: ISO Week, Thu 13:00 KST, UTC 저장

## 상태
확정 (Accepted)

## 맥락

보고 시스템은 "주간" 단위로 작동한다. 다음을 정의해야 한다:

1. **주(week) 식별:** 주를 어떻게 표현할 것인가?
   - 월요일 시작? 일요일 시작?
   - Monday 1월 1일은 주몇 주에 속하는가?

2. **마감 시간:** 제출 마감은 언제?
   - 목 13:00? (한국 시간)
   - 자정? (어느 시간대?)

3. **timestamp 저장:** DB에는 어느 시간대로 저장?
   - UTC? 로컬(KST)?

## 결정

### 1. week_key: ISO 8601 (ISO week)
- 형식: "YYYY-Www" (예: "2026-W23")
- ISO week는 월요일부터 시작, 1월 4일을 포함하는 주가 W01
- 전 세계 표준, 모호함 없음

### 2. 마감: 목 13:00 KST
- 매주 목요일 오후 1시 (Asia/Seoul timezone)
- Python zoneinfo 또는 pytz로 관리
- 한국은 DST 없음 (UTC+9 고정)

### 3. DB timestamp: UTC 저장
- 모든 submitted_at, created_at, updated_at은 UTC로 저장
- 조회 시 필요한 시간대로 변환 (클라이언트 또는 서버)
- 분산 시스템에서 시간 혼란 방지

## 근거

### 1. ISO Week의 명확성
- ISO 8601은 국제 표준
- 월요일 시작으로 비즈니스 주간과 일치
- "2026-W23"은 2026년 23주를 명확히 지칭
- 계산이 deterministic함

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Thu of 2026-W23
week_key = "2026-W23"
year, week = map(int, week_key.split("-W"))
# ISO week to date
from datetime import datetime, timedelta
jan4 = datetime(year, 1, 4)
week1_monday = jan4 - timedelta(days=jan4.weekday())
thursday = week1_monday + timedelta(weeks=week-1, days=3)
# thursday = 2026-06-04
```

### 2. 목 13:00 KST 마감
- 오전 근무 후 정리할 시간 충분
- 오후 업무에 방해 적음
- 팀장이 오후 내로 승인 가능
- 전 조직 일정상 합리적

### 3. UTC 저장의 이점
- 서버 타임존 변경해도 데이터 일관성 유지
- 다중 시간대 팀 지원 가능 (향후)
- 클라우드 환경에서 표준 관행

```python
# UTC로 저장
submitted_at_utc = datetime.now(timezone.utc)

# 조회 시 KST로 변환
kst = ZoneInfo("Asia/Seoul")
submitted_at_kst = submitted_at_utc.astimezone(kst)
```

## 결과

### 긍정
- **표준성:** ISO week는 국제 표준
- **명확성:** week_key는 모호함 없이 주를 식별
- **일관성:** UTC 저장으로 분산 시스템 안정
- **유지보수:** 시간대 변경 시에도 데이터 무결성 유지

### 부작용
- **시간대 계산:** 마감 판단은 항상 서버 로직 (클라이언트 신뢰하지 않음)
- **개발 복잡도:** timezone 관리 필요 (zoneinfo, pytz)
- **테스트:** 시간대 경계 케이스 테스트 필수 (목 12:59:59, 13:00:00, 13:00:01)

### 제약
- **고정된 마감:** 모든 채널이 목 13:00 KST로 고정 (채널별 조정 불가)
- **시간대 변경:** 만약 조직이 해외로 이전하면 새 ADR 필요

## 구현 체크리스트

- [ ] week_key 계산 함수: get_week_key_for_date(date) → "YYYY-Www"
- [ ] 마감 계산 함수: get_week_deadline(week_key) → datetime(UTC)
- [ ] submitted_after_deadline 판단: datetime.now(UTC) > get_week_deadline(week_key)
- [ ] DB: 모든 timestamp 컬럼 UTC로 정의 (datetime with timezone)
- [ ] 감시 로그: 마감 여부 기록 (submitted_after_deadline boolean)
- [ ] 테스트: 목 12:59:59.999 vs 13:00:00.000 경계 테스트

## Code Example

```python
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

class WeekUtils:
    @staticmethod
    def get_week_key(date: datetime) -> str:
        """Get ISO week key from date (e.g., '2026-W23')"""
        iso_cal = date.isocalendar()
        return f"{iso_cal.year}-W{iso_cal.week:02d}"

    @staticmethod
    def get_week_deadline(week_key: str) -> datetime:
        """Get Thu 13:00 KST for given week, return as UTC"""
        year, week = map(int, week_key.split("-W"))

        # Calculate Monday of that week
        jan4 = datetime(year, 1, 4)
        week1_monday = jan4 - timedelta(days=jan4.weekday())
        week_monday = week1_monday + timedelta(weeks=week-1)

        # Thursday is 3 days after Monday
        week_thursday = week_monday + timedelta(days=3)

        # Set to 13:00 KST
        kst = ZoneInfo("Asia/Seoul")
        deadline_kst = week_thursday.replace(hour=13, minute=0, second=0, microsecond=0)
        deadline_kst = deadline_kst.replace(tzinfo=kst)

        # Convert to UTC
        deadline_utc = deadline_kst.astimezone(timezone.utc)
        return deadline_utc

    @staticmethod
    def is_after_deadline(submitted_at: datetime) -> bool:
        """Check if submitted_at is after deadline (assumes UTC)"""
        week_key = WeekUtils.get_week_key(submitted_at.astimezone(ZoneInfo("Asia/Seoul")))
        deadline_utc = WeekUtils.get_week_deadline(week_key)
        return submitted_at > deadline_utc

# Usage
now_utc = datetime.now(timezone.utc)
week_key = WeekUtils.get_week_key(now_utc.astimezone(ZoneInfo("Asia/Seoul")))
# week_key = "2026-W23"

deadline_utc = WeekUtils.get_week_deadline(week_key)
# deadline_utc = 2026-06-04 04:00:00+00:00 (13:00 KST = 04:00 UTC)

is_late = WeekUtils.is_after_deadline(now_utc)
```

## 참고

- [ISO 8601 Week Date](https://en.wikipedia.org/wiki/ISO_week_date)
- [Python zoneinfo](https://docs.python.org/3/library/zoneinfo.html)
- [Python datetime](https://docs.python.org/3/library/datetime.html)
