import os
import sys
import argparse
import asyncio
import json
from dotenv import load_dotenv
from openai import AsyncOpenAI

# --- AI Configuration ---
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("OPENAI_BASE_URL")
MODEL_NAME = os.getenv("OPENAI_MODEL_NAME")

# Check configuration
if not all([API_KEY, BASE_URL, MODEL_NAME]):
    sys.exit("错误：请确保在 .env 文件中完整设置了 OPENAI_API_KEY, OPENAI_BASE_URL 和 OPENAI_MODEL_NAME。")

# Initialize OpenAI client
try:
    client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)
except Exception as e:
    sys.exit(f"初始化 OpenAI 客户端时出错: {e}")

# The meta-prompt to instruct the AI
META_PROMPT_TEMPLATE = """
你是一位世界级的AI提示词工程大师。你的任务是根据用户提供的【购买需求】，模仿一个【参考范例】，为闲鱼监控机器人的AI分析模块（代号 EagleEye）生成一份全新的【分析标准】文本。

你的输出必须严格遵循【参考范例】的结构、语气和核心原则，但内容要完全针对用户的【购买需求】进行定制。最终生成的文本将作为AI分析模块的思考指南。

---
这是【参考范例】（`macbook_criteria.txt`）：
```text
{reference_text}
```
---

这是用户的【购买需求】：
```text
{user_description}
```
---

请现在开始生成全新的【分析标准】文本。请注意：
1.  **只输出新生成的文本内容**，不要包含任何额外的解释、标题或代码块标记。
2.  保留范例中的 `[V6.3 核心升级]`、`[V6.4 逻辑修正]` 等版本标记，这有助于保持格式一致性。
3.  将范例中所有与 "MacBook" 相关的内容，替换为与用户需求商品相关的内容。
4.  思考并生成针对新商品类型的“一票否决硬性原则”和“危险信号清单”。
"""

async def generate_criteria(user_description: str, reference_file_path: str) -> str:
    """
    Generates a new criteria file content using AI.
    """
    print(f"正在读取参考文件: {reference_file_path}")
    try:
        with open(reference_file_path, 'r', encoding='utf-8') as f:
            reference_text = f.read()
    except FileNotFoundError:
        sys.exit(f"错误: 参考文件未找到: {reference_file_path}")
    except IOError as e:
        sys.exit(f"错误: 读取参考文件失败: {e}")

    print("正在构建发送给AI的指令...")
    prompt = META_PROMPT_TEMPLATE.format(
        reference_text=reference_text,
        user_description=user_description
    )

    print("正在调用AI生成新的分析标准，请稍候...")
    try:
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5, # Lower temperature for more predictable structure
        )
        generated_text = response.choices[0].message.content
        print("AI已成功生成内容。")
        return generated_text.strip()
    except Exception as e:
        sys.exit(f"调用 OpenAI API 时出错: {e}")


async def main():
    parser = argparse.ArgumentParser(
        description="使用AI根据用户需求和参考范例，生成闲鱼监控机器人的分析标准文件，并自动更新config.json。",
        epilog="""
使用示例:
  python prompt_generator.py \\
    --description "我想买一台95新以上的索尼A7M4相机，预算在10000到13000元之间..." \\
    --output prompts/sony_a7m4_criteria.txt \\
    --task-name "Sony A7M4" \\
    --keyword "a7m4" \\
    --min-price "10000" \\
    --max-price "13000"
""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--description", type=str, required=True, help="你详细的购买需求描述。")
    parser.add_argument("--output", type=str, required=True, help="新生成的分析标准文件的保存路径。")
    parser.add_argument("--reference", type=str, default="prompts/macbook_criteria.txt", help="作为模仿范例的参考文件路径。")
    # New arguments for config.json
    parser.add_argument("--task-name", type=str, required=True, help="新任务的名称 (例如: 'Sony A7M4')。")
    parser.add_argument("--keyword", type=str, required=True, help="新任务的搜索关键词 (例如: 'a7m4')。")
    parser.add_argument("--min-price", type=str, help="最低价格。")
    parser.add_argument("--max-price", type=str, help="最高价格。")
    parser.add_argument("--max-pages", type=int, default=3, help="最大搜索页数 (默认: 3)。")
    parser.add_argument('--no-personal-only', dest='personal_only', action='store_false', help="如果设置，则不筛选个人卖家。")
    parser.set_defaults(personal_only=True)
    parser.add_argument("--config-file", type=str, default="config.json", help="任务配置文件的路径 (默认: config.json)。")
    args = parser.parse_args()

    # Ensure the output directory exists
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    generated_criteria = await generate_criteria(args.description, args.reference)

    if generated_criteria:
        try:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(generated_criteria)
            print(f"\n成功！新的分析标准已保存到: {args.output}")
        except IOError as e:
            sys.exit(f"错误: 写入输出文件失败: {e}")

        # Now, update config.json
        print(f"正在更新配置文件: {args.config_file}")
        try:
            # Read existing config
            config_data = []
            if os.path.exists(args.config_file):
                with open(args.config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)

            # Create new task entry
            new_task = {
                "task_name": args.task_name,
                "enabled": True,
                "keyword": args.keyword,
                "max_pages": args.max_pages,
                "personal_only": args.personal_only,
                "ai_prompt_base_file": "prompts/base_prompt.txt",
                "ai_prompt_criteria_file": args.output
            }
            if args.min_price:
                new_task["min_price"] = args.min_price
            if args.max_price:
                new_task["max_price"] = args.max_price

            # Append new task
            config_data.append(new_task)

            # Write back to config file
            with open(args.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            
            print(f"成功！新任务 '{args.task_name}' 已添加到 {args.config_file} 并已启用。")
            print("现在，你可以直接运行 `python spider_v2.py` 来启动包括新任务在内的所有监控。")

        except FileNotFoundError:
            # This case is handled by os.path.exists, but kept for safety
            sys.exit(f"错误: 配置文件未找到: {args.config_file}")
        except json.JSONDecodeError:
            sys.exit(f"错误: 配置文件 {args.config_file} 格式错误，无法解析。")
        except IOError as e:
            sys.exit(f"错误: 读写配置文件失败: {e}")

if __name__ == "__main__":
    asyncio.run(main())
