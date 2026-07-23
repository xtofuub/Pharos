from __future__ import annotations
import pytest
from breachelens.db import Database
from breachelens.index.query import SearchRequest,execute_search

@pytest.mark.asyncio
async def test_regex_search_is_real_regex(tmp_path):
    db=Database(tmp_path/"pharos.db");await db.connect();await db.run_migrations()
    await db.execute("INSERT INTO sources(path) VALUES (?)",(str(tmp_path),));source_id=await db.fetchval("SELECT id FROM sources LIMIT 1")
    await db.execute("INSERT INTO files(source_id,path,file_name,extension,size_bytes,mtime,status) VALUES (?,?,?,?,?,?, 'indexed')",(source_id,str(tmp_path/"a.txt"),"a.txt","txt",10,1));file_id=await db.fetchval("SELECT id FROM files LIMIT 1")
    text="user-481@example.com"
    fts=await db.execute("INSERT INTO records_fts(searchable_text,source_id,file_id,file_path,file_name,extension,line_number,byte_offset,byte_length,record_format,record_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?)",(text,source_id,file_id,str(tmp_path/"a.txt"),"a.txt","txt",1,0,len(text),"text","h1"))
    await db.execute("INSERT INTO records(fts_rowid,source_id,file_id,file_path,file_name,extension,line_number,byte_offset,byte_length,record_format,searchable_text,record_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(fts.lastrowid,source_id,file_id,str(tmp_path/"a.txt"),"a.txt","txt",1,0,len(text),"text",text,"h1"))
    result=await execute_search(db,SearchRequest(query=r"user-\d{3}@example\.com",mode="regex"));assert result["total"]==1
    await db.close()
