import uvicorn
import json
import aiofiles
import os
import glob
import asyncio
from dotenv import dotenv_values
from fastapi import FastAPI, Request, HTTPException
from prompt_generator import generate_criteria, update_config_with_new_task
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional


class Task(BaseModel):
    task_name: str
    enabled: bool
    keyword: str
    max_pages: int
    personal_only: bool
    min_price: Optional[str] = None
    max_price: Optional[str] = None
    ai_prompt_base_file: str
    ai_prompt_criteria_file: str


class TaskUpdate(BaseModel):
    task_name: Optional[str] = None
    enabled: Optional[bool] = None
    keyword: Optional[str] = None
    max_pages: Optional[int] = None
    personal_only: Optional[bool] = None
    min_price: Optional[str] = None
    max_price: Optional[str] = None
    ai_prompt_base_file: Optional[str] = None
    ai_prompt_criteria_file: Optional[str] = None


class TaskGenerateRequest(BaseModel):
    task_name: str
    keyword: str
    description: str
    personal_only: bool = True
    min_price: Optional[str] = None
    max_price: Optional[str] = None


class PromptUpdate(BaseModel):
    content: str


app = FastAPI(title="闲鱼智能监控机器人")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """
    提供 Web UI 的主页面。
    """
    return templates.TemplateResponse("index.html", {"request": request})

# --- API Endpoints ---

CONFIG_FILE = "config.json"

@app.get("/api/tasks")
async def get_tasks():
    """
    读取并返回 config.json 中的所有任务。
    """
    try:
        async with aiofiles.open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            content = await f.read()
            tasks = json.loads(content)
            # 为每个任务添加一个唯一的 id
            for i, task in enumerate(tasks):
                task['id'] = i
            return tasks
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"配置文件 {CONFIG_FILE} 未找到。")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"配置文件 {CONFIG_FILE} 格式错误。")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取任务配置时发生错误: {e}")


@app.post("/api/tasks/generate", response_model=dict)
async def generate_task(req: TaskGenerateRequest):
    """
    使用 AI 生成一个新的分析标准文件，并据此创建一个新任务。
    """
    print(f"收到 AI 任务生成请求: {req.task_name}")
    
    # 1. 为新标准文件生成一个唯一的文件名
    safe_keyword = "".join(c for c in req.keyword.lower().replace(' ', '_') if c.isalnum() or c in "_-").rstrip()
    output_filename = f"prompts/{safe_keyword}_criteria.txt"
    
    # 2. 调用 AI 生成分析标准
    try:
        generated_criteria = await generate_criteria(
            user_description=req.description,
            reference_file_path="prompts/macbook_criteria.txt" # 使用默认的macbook标准作为参考
        )
        if not generated_criteria:
            raise HTTPException(status_code=500, detail="AI未能生成分析标准。")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"调用AI生成标准时出错: {e}")

    # 3. 将生成的文本保存到新文件
    try:
        os.makedirs("prompts", exist_ok=True)
        async with aiofiles.open(output_filename, 'w', encoding='utf-8') as f:
            await f.write(generated_criteria)
        print(f"新的分析标准已保存到: {output_filename}")
    except IOError as e:
        raise HTTPException(status_code=500, detail=f"保存分析标准文件失败: {e}")

    # 4. 创建新任务对象
    new_task = {
        "task_name": req.task_name,
        "enabled": True,
        "keyword": req.keyword,
        "max_pages": 3, # 默认值
        "personal_only": req.personal_only,
        "min_price": req.min_price,
        "max_price": req.max_price,
        "ai_prompt_base_file": "prompts/base_prompt.txt",
        "ai_prompt_criteria_file": output_filename
    }

    # 5. 将新任务添加到 config.json
    success = await update_config_with_new_task(new_task, CONFIG_FILE)
    if not success:
        # 如果更新失败，最好能把刚刚创建的文件删掉，以保持一致性
        if os.path.exists(output_filename):
            os.remove(output_filename)
        raise HTTPException(status_code=500, detail="更新配置文件 config.json 失败。")

    # 6. 返回成功创建的任务（包含ID）
    async with aiofiles.open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        tasks = json.loads(await f.read())
    new_task_with_id = new_task.copy()
    new_task_with_id['id'] = len(tasks) - 1

    return {"message": "AI 任务创建成功。", "task": new_task_with_id}


@app.post("/api/tasks", response_model=dict)
async def create_task(task: Task):
    """
    创建一个新任务并将其添加到 config.json。
    """
    try:
        async with aiofiles.open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            tasks = json.loads(await f.read())
    except (FileNotFoundError, json.JSONDecodeError):
        tasks = []

    new_task_data = task.dict()
    tasks.append(new_task_data)

    try:
        async with aiofiles.open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(tasks, ensure_ascii=False, indent=2))
        
        new_task_data['id'] = len(tasks) - 1
        return {"message": "任务创建成功。", "task": new_task_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入配置文件时发生错误: {e}")


@app.patch("/api/tasks/{task_id}", response_model=dict)
async def update_task(task_id: int, task_update: TaskUpdate):
    """
    更新指定ID任务的属性。
    """
    try:
        async with aiofiles.open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            tasks = json.loads(await f.read())
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=500, detail=f"读取或解析配置文件失败: {e}")

    if not (0 <= task_id < len(tasks)):
        raise HTTPException(status_code=404, detail="任务未找到。")

    # 更新数据
    task_changed = False
    update_data = task_update.dict(exclude_unset=True)
    
    if update_data:
        original_task = tasks[task_id].copy()
        tasks[task_id].update(update_data)
        if tasks[task_id] != original_task:
            task_changed = True

    if not task_changed:
        return JSONResponse(content={"message": "数据无变化，未执行更新。"}, status_code=200)

    # 异步写回文件
    try:
        async with aiofiles.open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(tasks, ensure_ascii=False, indent=2))
        
        updated_task = tasks[task_id]
        updated_task['id'] = task_id
        return {"message": "任务更新成功。", "task": updated_task}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入配置文件时发生错误: {e}")


@app.delete("/api/tasks/{task_id}", response_model=dict)
async def delete_task(task_id: int):
    """
    从 config.json 中删除指定ID的任务。
    """
    try:
        async with aiofiles.open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            tasks = json.loads(await f.read())
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=500, detail=f"读取或解析配置文件失败: {e}")

    if not (0 <= task_id < len(tasks)):
        raise HTTPException(status_code=404, detail="任务未找到。")

    deleted_task = tasks.pop(task_id)

    try:
        async with aiofiles.open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(tasks, ensure_ascii=False, indent=2))
        
        return {"message": "任务删除成功。", "task_name": deleted_task.get("task_name")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入配置文件时发生错误: {e}")


@app.get("/api/results/files")
async def list_result_files():
    """
    列出所有生成的 .jsonl 结果文件。
    """
    files = glob.glob("*.jsonl")
    return {"files": files}


@app.get("/api/results/{filename}")
async def get_result_file_content(filename: str, page: int = 1, limit: int = 20, recommended_only: bool = False):
    """
    读取指定的 .jsonl 文件内容，支持分页和筛选。
    """
    if not filename.endswith(".jsonl") or "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="无效的文件名。")
    
    if not os.path.exists(filename):
        raise HTTPException(status_code=404, detail="结果文件未找到。")

    results = []
    try:
        async with aiofiles.open(filename, 'r', encoding='utf-8') as f:
            async for line in f:
                try:
                    record = json.loads(line)
                    if recommended_only:
                        if record.get("ai_analysis", {}).get("is_recommended") is True:
                            results.append(record)
                    else:
                        results.append(record)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取结果文件时出错: {e}")

    results.reverse()
    
    total_items = len(results)
    start = (page - 1) * limit
    end = start + limit
    paginated_results = results[start:end]

    return {
        "total_items": total_items,
        "page": page,
        "limit": limit,
        "items": paginated_results
    }


@app.get("/api/settings/status")
async def get_system_status():
    """
    检查系统关键文件和配置的状态。
    """
    env_config = dotenv_values(".env")
    
    status = {
        "login_state_file": {
            "exists": os.path.exists("xianyu_state.json"),
            "path": "xianyu_state.json"
        },
        "env_file": {
            "exists": os.path.exists(".env"),
            "openai_api_key_set": bool(env_config.get("OPENAI_API_KEY")),
            "openai_base_url_set": bool(env_config.get("OPENAI_BASE_URL")),
            "openai_model_name_set": bool(env_config.get("OPENAI_MODEL_NAME")),
            "ntfy_topic_url_set": bool(env_config.get("NTFY_TOPIC_URL")),
        }
    }
    return status


PROMPTS_DIR = "prompts"

@app.get("/api/prompts")
async def list_prompts():
    """
    列出 prompts/ 目录下的所有 .txt 文件。
    """
    if not os.path.isdir(PROMPTS_DIR):
        return []
    return [f for f in os.listdir(PROMPTS_DIR) if f.endswith(".txt")]


@app.get("/api/prompts/{filename}")
async def get_prompt_content(filename: str):
    """
    获取指定 prompt 文件的内容。
    """
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="无效的文件名。")
    
    filepath = os.path.join(PROMPTS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Prompt 文件未找到。")
    
    async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
        content = await f.read()
    return {"filename": filename, "content": content}


@app.put("/api/prompts/{filename}")
async def update_prompt_content(filename: str, prompt_update: PromptUpdate):
    """
    更新指定 prompt 文件的内容。
    """
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="无效的文件名。")

    filepath = os.path.join(PROMPTS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Prompt 文件未找到。")

    try:
        async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
            await f.write(prompt_update.content)
        return {"message": f"Prompt 文件 '{filename}' 更新成功。"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入 Prompt 文件时出错: {e}")


if __name__ == "__main__":
    print("启动 Web 管理界面，请在浏览器访问 http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
