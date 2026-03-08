# 벌크 스케줄 CSV/Excel 템플릿

블로그 포스팅을 여러 건 예약할 때 사용하는 파일 형식입니다.

## 지원 형식

- **CSV** (UTF-8): `bulk_schedule_template.csv` 사용 후 업로드
- **Excel** (.xlsx): 동일 컬럼으로 작성 후 업로드

## 컬럼 설명

| 컬럼 | 필수 | 설명 | 예시 |
|------|------|------|------|
| topic | ✅ | 포스팅 주제(검색용) | 서울 벚꽃 개화시기 |
| run_at | ✅ | 예약 실행 일시 | 2025-04-01 09:00:00 |
| main_topic | | 글의 메인 주제 (비우면 topic 사용) | 서울 벚꽃 개화시기 |
| sub_topics | | 세부 주제 (쉼표 구분) | 개화 예측,명소,축제 |
| prompt_folder | | 글 작성 가이드 폴더명 | 벚꽃 개화시기 |
| image_count | | 이미지 장수 (1~5) | 4 |
| status | | 발행 상태 | draft, publish, private |
| model | | OpenAI 모델 | gpt-4o-mini |
| with_image | | 이미지 포함 여부 | true, false, 1, 0 |
| image_source | | 이미지 소스 | local, title, dalle, pixabay |
| submit_search | | 검색엔진 제출 여부 | true, false |
| sitemap_url | | 사이트맵 URL | https://... |

## image_source 값

- **local** : 프롬프트 폴더에 넣어둔 이미지 사용
- **title** : 주제 기반 썸네일 자동 생성 (무료)
- **dalle** : DALL-E AI 이미지 생성 (유료)
- **pixabay** : Pixabay 스톡 이미지 검색

## 예시 (CSV)

```csv
topic,run_at,main_topic,sub_topics,prompt_folder,image_count,status,model,with_image,image_source,submit_search,sitemap_url
서울 벚꽃 개화시기,2025-04-01 09:00:00,서울 벚꽃 개화시기,"개화,명소",벚꽃 개화시기,4,draft,gpt-4o-mini,true,title,false,
```
