document.addEventListener('DOMContentLoaded', function() {
    const mainContent = document.getElementById('main-content');
    const navLinks = document.querySelectorAll('.nav-link');

    // --- Templates for each section ---
    const templates = {
        tasks: () => `
            <section id="tasks-section" class="content-section">
                <div class="section-header">
                    <h2>任务管理</h2>
                    <button id="add-task-btn" class="control-button primary-btn">➕ 创建新任务</button>
                </div>
                <div id="tasks-table-container">
                    <p>正在加载任务列表...</p>
                </div>
            </section>`,
        results: () => `
            <section id="results-section" class="content-section">
                <h2>结果查看</h2>
                <p>这里将提供一个下拉菜单选择任务，然后以卡片形式展示对应的 .jsonl 文件中的商品。</p>
                <p>将支持筛选“仅看AI推荐”的商品，并可以查看AI分析详情。</p>
            </section>`,
        settings: () => `
            <section id="settings-section" class="content-section">
                <h2>系统设置</h2>
                <p>这里将管理项目的核心配置。</p>
                <ul>
                    <li><strong>登录状态:</strong> 检查 xianyu_state.json 文件是否存在并有效。</li>
                    <li><strong>环境变量:</strong> 管理 .env 文件中的 OpenAI 和 ntfy 配置。</li>
                    <li><strong>Prompt 模板:</strong> 在线查看和编辑 prompts/ 目录下的分析标准文件。</li>
                </ul>
            </section>`
    };

    // --- API Functions ---
    async function updateTask(taskId, data) {
        try {
            const response = await fetch(`/api/tasks/${taskId}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data),
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || '更新任务失败');
            }
            console.log(`任务 ${taskId} 更新成功!`);
            return await response.json();
        } catch (error) {
            console.error(`无法更新任务 ${taskId}:`, error);
            // TODO: Use a more elegant notification system
            alert(`错误: ${error.message}`);
            return null;
        }
    }

    async function fetchTasks() {
        try {
            const response = await fetch('/api/tasks');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            console.error("无法获取任务列表:", error);
            return null;
        }
    }

    // --- Render Functions ---
    function renderTasksTable(tasks) {
        if (!tasks || tasks.length === 0) {
            return '<p>没有找到任何任务。请点击右上角“创建新任务”来添加一个。</p>';
        }

        const tableHeader = `
            <thead>
                <tr>
                    <th>启用</th>
                    <th>任务名称</th>
                    <th>关键词</th>
                    <th>价格范围</th>
                    <th>筛选条件</th>
                    <th>操作</th>
                </tr>
            </thead>`;

        const tableBody = tasks.map(task => `
            <tr data-task-id="${task.id}">
                <td>
                    <label class="switch">
                        <input type="checkbox" ${task.enabled ? 'checked' : ''}>
                        <span class="slider round"></span>
                    </label>
                </td>
                <td>${task.task_name}</td>
                <td><span class="tag">${task.keyword}</span></td>
                <td>${task.min_price || '不限'} - ${task.max_price || '不限'}</td>
                <td>${task.personal_only ? '<span class="tag personal">个人闲置</span>' : ''}</td>
                <td>
                    <button class="action-btn edit-btn">编辑</button>
                    <button class="action-btn delete-btn">删除</button>
                </td>
            </tr>`).join('');

        return `<table class="tasks-table">${tableHeader}<tbody>${tableBody}</tbody></table>`;
    }


    async function navigateTo(hash) {
        const sectionId = hash.substring(1) || 'tasks';

        // Update nav links active state
        navLinks.forEach(link => {
            link.classList.toggle('active', link.getAttribute('href') === `#${sectionId}`);
        });

        // Update main content
        if (templates[sectionId]) {
            mainContent.innerHTML = templates[sectionId]();
            // Make the new content visible
            const newSection = mainContent.querySelector('.content-section');
            if (newSection) {
                requestAnimationFrame(() => {
                    newSection.classList.add('active');
                });
            }

            // --- Load data for the current section ---
            if (sectionId === 'tasks') {
                const container = document.getElementById('tasks-table-container');
                const tasks = await fetchTasks();
                container.innerHTML = renderTasksTable(tasks);
            }

        } else {
            mainContent.innerHTML = '<section class="content-section active"><h2>页面未找到</h2></section>';
        }
    }

    // Handle navigation clicks
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const hash = this.getAttribute('href');
            if (window.location.hash !== hash) {
                window.location.hash = hash;
            }
        });
    });

    // Handle hash changes (e.g., back/forward buttons, direct URL)
    window.addEventListener('hashchange', () => {
        navigateTo(window.location.hash);
    });

    // --- Event Delegation for dynamic content ---
    mainContent.addEventListener('click', (event) => {
        const target = event.target;
        const button = target.closest('button'); // Find the closest button element
        if (!button) return;

        const row = button.closest('tr');
        const taskId = row ? row.dataset.taskId : null;

        if (button.matches('.edit-btn')) {
            alert(`编辑功能待实现 (任务ID: ${taskId})`);
        } else if (button.matches('.delete-btn')) {
            alert(`删除功能待实现 (任务ID: ${taskId})`);
        } else if (button.matches('#add-task-btn')) {
            alert('创建新任务功能待实现');
        }
    });

    mainContent.addEventListener('change', async (event) => {
        const target = event.target;
        // Check if the changed element is a toggle switch
        if (target.matches('.tasks-table input[type="checkbox"]')) {
            const row = target.closest('tr');
            const taskId = row.dataset.taskId;
            const isEnabled = target.checked;

            if (taskId) {
                await updateTask(taskId, { enabled: isEnabled });
                // The visual state is already updated by the checkbox itself.
                // We could add a small "saved" indicator here in the future.
            }
        }
    });

    // Initial load
    navigateTo(window.location.hash || '#tasks');

    // --- Header Controls Event Listeners ---
    document.getElementById('start-all-tasks').addEventListener('click', () => {
        alert('“全部启动”功能待实现');
    });

    document.getElementById('stop-all-tasks').addEventListener('click', () => {
        alert('“全部停止”功能待实现');
    });
});
