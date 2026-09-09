import pandas as pd
from sqlalchemy import text

from pilos.storage.db import get_engine


# [변경 2026-08-03] select_unprocessed_source_comment_files() 를 이 함수로 교체.
#   이전: WHERE NOT EXISTS 로 '전처리 행이 하나도 없는 파일'만 반환 → 파일당 1회만
#         처리. 하루 종일 append 되는 작성일별 파일은 첫 처리 이후 추가분이 누락됐다.
#   이후: LEFT JOIN + MAX(raw_line_number) 로 '모든 파일 + 처리 완료 줄번호'를 반환.
#         호출자가 그 줄번호 이후 새 줄만 이어서 처리한다(줄 단위 watermark).
def select_source_files_with_watermark(
    target_date: str | None = None,
    include_backfill: bool = False,
) -> list[dict]:
    """원본파일 정보 + 이미 전처리된 마지막 줄번호(watermark)를 반환한다.

    target_date:
        - None  → 전 파일 스캔(배치용). include_backfill 로 대상 범위를 고른다.
        - 'YYYYMMDD' → 파일명에 그 날짜가 든 파일만 (실시간, 전 파일 스캔 회피).
          이 경우 include_backfill 은 무시된다(날짜 필터가 우선).

    include_backfill (target_date=None 일 때만 의미):
        - False(기본) → from_ 증분 파일만. 백필을 더 안 하면 until_ 는 정적이라
          매 실행 재스캔이 낭비이므로 기본 제외(비용 절감).
        - True  → from_ + until_ 모두. 초기 전체 적재·백필 직후 catch-up 등 특수 상황.

    processed_line = 해당 파일에서 preprocessed_comment 에 적재된 raw_line_number 의
    최댓값(아직 하나도 없으면 0). 호출자는 이 줄번호를 넘는 새 줄만 전처리하면 된다.

    작성일별 파일은 하루 종일 append 로 자라므로, '파일 존재 여부(WHERE NOT EXISTS)'로
    한 번만 처리하면 첫 처리 이후 추가분이 누락된다. 줄번호 watermark 로 바꿔
    자란 파일의 새 줄만 이어서 처리한다(1분 간격 증분 대응).
    """

    start_sql = '''
        SELECT
            scf.source_comment_file_id,
            scf.stock_id,
            scf.file_name,
            scf.file_path,
            scf.file_ext,
            COALESCE(MAX(pc.raw_line_number), 0) AS processed_line
        FROM source_comment_file AS scf
        LEFT JOIN preprocessed_comment AS pc
            ON pc.source_comment_file_id = scf.source_comment_file_id
    '''
    end_sql = '''
        GROUP BY
            scf.source_comment_file_id,
            scf.stock_id,
            scf.file_name,
            scf.file_path,
            scf.file_ext
    '''
    # 기본: from_ 증분 파일만. include_backfill=True 면 until_ 백필 파일도 포함.
    middle_sql = "WHERE scf.file_name LIKE 'from%'"
    if include_backfill:
        middle_sql = "WHERE scf.file_name LIKE 'from%' OR scf.file_name LIKE 'until%'"

    if isinstance(target_date, str):
        middle_sql = '''
            WHERE scf.file_name LIKE CONCAT('%', :target_date, '%')
        '''
    sql = text(start_sql + middle_sql + end_sql)
        

    # 원본파일마다 전처리 테이블에 적재된 raw_line_number 최댓값을 함께 가져온다
    # (LEFT JOIN + MAX: 아직 전처리 안 된 파일은 processed_line=0).
    engine = get_engine()

    with engine.connect() as conn:
        # target_date 가 문자열일 때만 바인드 파라미터를 넘긴다.
        # None 이면 기본 필터(from% OR until%)라 :target_date 자리가 없으므로 바인드를 넘기지 않는다.
        if isinstance(target_date, str):
            result = conn.execute(sql, {"target_date": target_date})
        else:
            result = conn.execute(sql)

        # SQLAlchemy RowMapping을 jobs 계층에서 사용할 일반 dict 목록으로 변환
        return [
            dict(row)
            for row in result.mappings()
        ]


# [변경 2026-08-03] 단일 파일 조회 신설.
#   증분 러너는 방금 기록한 파일(≤2개)만 전처리하면 되므로, 전 파일 스캔 대신
#   파일명으로 그 파일의 source_comment_file_id + watermark 만 한 번에 가져온다.
def select_source_file_by_name(file_name: str) -> dict | None:
    """파일명으로 원본파일 정보 + watermark(processed_line)를 1건 조회한다(없으면 None).

    증분 러너가 방금 append 한 파일 하나만 이어서 전처리할 때 쓴다(전 파일 스캔 회피).
    processed_line = 해당 파일에서 preprocessed_comment 에 적재된 raw_line_number 최댓값(없으면 0).
    """
    sql = text("""
        SELECT
            scf.source_comment_file_id,
            scf.stock_id,
            scf.file_name,
            scf.file_path,
            scf.file_ext,
            COALESCE(MAX(pc.raw_line_number), 0) AS processed_line
        FROM source_comment_file AS scf
        LEFT JOIN preprocessed_comment AS pc
            ON pc.source_comment_file_id = scf.source_comment_file_id
        WHERE scf.file_name = :file_name
        GROUP BY
            scf.source_comment_file_id,
            scf.stock_id,
            scf.file_name,
            scf.file_path,
            scf.file_ext
    """)
    engine = get_engine()

    with engine.connect() as conn:
        result = conn.execute(sql, {"file_name": file_name})
        rows = [dict(row) for row in result.mappings()]
    # 파일명은 UNIQUE 라 최대 1건. 없으면(등록 전) None.
    return rows[0] if rows else None

def insert_preprocessed_comments(
        processed_df: pd.DataFrame,
    ) -> int:
        """
        전처리 완료된 데이터를 적재한다.
        """
        sql = text("""
            INSERT IGNORE INTO preprocessed_comment (
            comment_id, 
            stock_id, 
            title, 
            message, 
            text, 
            like_count,
            parent_id, 
            created_at, 
            updated_at, 
            raw_line_number, 
            source_comment_file_id
            )
            VALUES (
            :comment_id, 
            :stock_id, 
            :title, 
            :message, 
            :text, 
            :like_count, 
            :parent_id, 
            :created_at, 
            :updated_at, 
            :raw_line_number, 
            :source_comment_file_id
            )
            """)
        # DataFrame 각 행을 SQLAlchemy executemany에 전달할 파라미터 목록으로 변환
        records = processed_df.to_dict(orient="records")
        # 빈 입력에서는 DB 연결과 빈 INSERT를 수행하지 않음
        if not records:
             return 0
        engine = get_engine()
        # 모든 입력 행을 하나의 트랜잭션으로 적재하고,
        # 예외 발생 시 전체 작업을 롤백
        with engine.begin() as conn:
            result = conn.execute(
                sql,
                records,
            )
            # INSERT IGNORE로 실제 삽입된 행 수를 반환
            inserted_count = result.rowcount

        return inserted_count
            



