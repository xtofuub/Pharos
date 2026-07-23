from __future__ import annotations
import pytest
from breachelens.db import Database
from breachelens.identities import canonicalize_email,get_profile,list_profiles,rebuild_identities

def test_gmail_aliases_share_identity():
    assert canonicalize_email("John.Smith+shop@googlemail.com")=="johnsmith@gmail.com"
    assert canonicalize_email("johnsmith@gmail.com")=="johnsmith@gmail.com"

@pytest.mark.asyncio
async def test_rebuild_profiles_bundles_repeated_emails(tmp_path):
    db=Database(tmp_path/"pharos.db");await db.connect();await db.run_migrations()
    await db.execute("INSERT INTO sources(path) VALUES (?)",(str(tmp_path),));source_id=await db.fetchval("SELECT id FROM sources LIMIT 1")
    await db.execute("INSERT INTO files(source_id,path,file_name,extension,size_bytes,mtime,status) VALUES (?,?,?,?,?,?, 'indexed')",(source_id,str(tmp_path/"a.txt"),"a.txt","txt",10,1));file_id=await db.fetchval("SELECT id FROM files LIMIT 1")
    for index,email in enumerate(("John.Smith+shop@gmail.com","johnsmith@googlemail.com"),start=1):
        fts=await db.execute("INSERT INTO records_fts(searchable_text,source_id,file_id,file_path,file_name,extension,line_number,byte_offset,byte_length,record_format,record_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?)",(email,source_id,file_id,str(tmp_path/"a.txt"),"a.txt","txt",index,0,len(email),"text",f"h{index}"))
        record=await db.execute("INSERT INTO records(fts_rowid,source_id,file_id,file_path,file_name,extension,line_number,byte_offset,byte_length,record_format,searchable_text,record_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(fts.lastrowid,source_id,file_id,str(tmp_path/"a.txt"),"a.txt","txt",index,0,len(email),"text",email,f"h{index}"))
        await db.execute("INSERT INTO record_entities(record_id,entity_type,value,normalized_value) VALUES (?,?,?,?)",(record.lastrowid,"email",email.lower(),canonicalize_email(email)))
        await db.execute("INSERT INTO record_entities(record_id,entity_type,value,normalized_value) VALUES (?,?,?,?)",(record.lastrowid,"username","johnsmith","johnsmith"))
    await rebuild_identities(db);result=await list_profiles(db)
    assert result["total"]==1 and result["profiles"][0]["record_count"]==2
    profile=await get_profile(db,result["profiles"][0]["id"]);assert profile is not None
    assert profile["entities"]["username"][0]["value"]=="johnsmith"
    await db.close()
