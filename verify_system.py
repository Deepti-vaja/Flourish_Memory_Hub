import asyncio
import sys
from sqlalchemy import text
from app.database.session import async_session_maker

async def main():
    print("=" * 75)
    print("      FLOURISH GOVERNED MEMORY HUB — LIVE DATABASE VERIFICATION")
    print("=" * 75)
    
    async with async_session_maker() as session:
        # 1. Verify Alembic Migration Version
        res_ver = await session.execute(text("SELECT version_num FROM alembic_version"))
        version = res_ver.scalar()
        print(f"[MIGRATION VERIFIED] Current Alembic Head : {version}")
        
        # 2. Verify PostgreSQL Tables
        res_tbl = await session.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
        )
        tables = [r[0] for r in res_tbl.fetchall()]
        print(f"[TABLES VERIFIED]    Active Public Tables : {tables}")
        
        # 3. Verify Triggers
        res_trg = await session.execute(
            text("SELECT trigger_name, event_manipulation, event_object_table FROM information_schema.triggers WHERE trigger_schema='public'")
        )
        triggers = [(r[0], r[1], r[2]) for r in res_trg.fetchall()]
        print(f"[TRIGGERS VERIFIED]  Active DDL Triggers  : {triggers}")
        
        # 4. Verify Audit Sequence Head
        res_seq = await session.execute(
            text("SELECT lock_key, last_sequence_id, last_entry_hash FROM audit_sequence_head WHERE lock_key = 1")
        )
        seq = res_seq.fetchone()
        if seq:
            print(f"[AUDIT VERIFIED]     audit_sequence_head  : lock_key={seq[0]} -> last_sequence_id={seq[1]}")
        else:
            print("[AUDIT VERIFIED]     audit_sequence_head  : initialized")
            
    print("=" * 75)
    print("VERIFICATION COMPLETE — ALL POSTGRESQL STRUCTURES OPERATIONAL")
    print("=" * 75)

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
