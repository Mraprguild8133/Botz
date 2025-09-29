from flask import Flask, render_template, jsonify
import json
import time
import psutil
import os
from datetime import datetime
import threading

app = Flask(__name__)

# Global variables
BOT_START_TIME = time.time()

def load_json(file_path):
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except:
        return {}

def get_uptime():
    uptime_seconds = int(time.time() - BOT_START_TIME)
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60
    seconds = uptime_seconds % 60
    return f"{days}d {hours}h {minutes}m {seconds}s"

def format_size(size_bytes):
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.2f} {size_names[i]}"

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/stats')
def get_stats():
    # System stats
    process = psutil.Process()
    memory_usage = process.memory_info().rss / 1024 / 1024
    cpu_usage = psutil.cpu_percent()
    disk_usage = psutil.disk_usage('.')
    
    # Bot stats
    users = load_json('users.json')
    stats = load_json('stats.json')
    
    total_users = len(users)
    
    # Active users (last 24 hours)
    day_ago = datetime.now().timestamp() - (24 * 60 * 60)
    active_users = sum(
        1 for user_data in users.values() 
        if datetime.fromisoformat(user_data["last_active"]).timestamp() > day_ago
    )
    
    # Today's stats
    today = datetime.now().strftime("%Y-%m-%d")
    today_stats = stats.get(today, {"files_processed": 0, "bytes_processed": 0})
    
    # Total files processed
    total_files = sum(user.get("files_processed", 0) for user in users.values())
    
    # Recent activity (last 7 days)
    recent_activity = {}
    for i in range(7):
        date = (datetime.now().timestamp() - (i * 24 * 60 * 60))
        date_str = datetime.fromtimestamp(date).strftime("%Y-%m-%d")
        day_stats = stats.get(date_str, {"files_processed": 0, "bytes_processed": 0})
        recent_activity[date_str] = day_stats
    
    return jsonify({
        'system': {
            'uptime': get_uptime(),
            'memory_usage': round(memory_usage, 2),
            'cpu_usage': round(cpu_usage, 2),
            'disk_used': format_size(disk_usage.used),
            'disk_total': format_size(disk_usage.total),
            'disk_percent': round((disk_usage.used / disk_usage.total) * 100, 2)
        },
        'bot': {
            'total_users': total_users,
            'active_users': active_users,
            'total_files_processed': total_files,
            'today_files': today_stats['files_processed'],
            'today_data': format_size(today_stats['bytes_processed'])
        },
        'recent_activity': recent_activity
    })

@app.route('/api/users')
def get_users():
    users = load_json('users.json')
    
    # Sort users by last activity
    sorted_users = sorted(
        users.items(),
        key=lambda x: datetime.fromisoformat(x[1]['last_active']),
        reverse=True
    )[:50]  # Show only last 50 users
    
    user_list = []
    for user_id, user_data in sorted_users:
        user_list.append({
            'user_id': user_id,
            'joined_at': user_data['joined_at'],
            'last_active': user_data['last_active'],
            'files_processed': user_data.get('files_processed', 0)
        })
    
    return jsonify(user_list)

@app.route('/api/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    # Create templates directory if not exists
    os.makedirs('templates', exist_ok=True)
    
    # Create dashboard template
    with open('templates/dashboard.html', 'w') as f:
        f.write('''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Turbo Bot Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { text-align: center; margin-bottom: 30px; }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); }
        .header p { font-size: 1.2em; opacity: 0.9; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: rgba(255,255,255,0.1); backdrop-filter: blur(10px); padding: 20px; border-radius: 15px; text-align: center; border: 1px solid rgba(255,255,255,0.2); }
        .stat-card h3 { font-size: 0.9em; opacity: 0.8; margin-bottom: 10px; }
        .stat-card .value { font-size: 2em; font-weight: bold; }
        .charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 30px; }
        .chart-container { background: rgba(255,255,255,0.1); backdrop-filter: blur(10px); padding: 20px; border-radius: 15px; border: 1px solid rgba(255,255,255,0.2); }
        .users-table { background: rgba(255,255,255,0.1); backdrop-filter: blur(10px); padding: 20px; border-radius: 15px; border: 1px solid rgba(255,255,255,0.2); }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); }
        th { opacity: 0.8; }
        .last-updated { text-align: center; margin-top: 20px; opacity: 0.7; }
        @media (max-width: 768px) {
            .charts-grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Turbo Bot Dashboard</h1>
            <p>Real-time monitoring and statistics</p>
        </div>
        
        <div class="stats-grid" id="statsGrid">
            <!-- Stats will be populated by JavaScript -->
        </div>
        
        <div class="charts-grid">
            <div class="chart-container">
                <canvas id="activityChart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="systemChart"></canvas>
            </div>
        </div>
        
        <div class="users-table">
            <h3>Recent Users</h3>
            <div id="usersTable">
                <!-- Users table will be populated by JavaScript -->
            </div>
        </div>
        
        <div class="last-updated" id="lastUpdated">
            Last updated: <span id="updateTime">Loading...</span>
        </div>
    </div>

    <script>
        let activityChart, systemChart;
        
        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                const data = await response.json();
                
                // Update stats grid
                document.getElementById('statsGrid').innerHTML = `
                    <div class="stat-card">
                        <h3>👥 Total Users</h3>
                        <div class="value">${data.bot.total_users}</div>
                    </div>
                    <div class="stat-card">
                        <h3>📊 Active Users (24h)</h3>
                        <div class="value">${data.bot.active_users}</div>
                    </div>
                    <div class="stat-card">
                        <h3>📁 Files Processed</h3>
                        <div class="value">${data.bot.total_files_processed}</div>
                    </div>
                    <div class="stat-card">
                        <h3>⚡ Files Today</h3>
                        <div class="value">${data.bot.today_files}</div>
                    </div>
                    <div class="stat-card">
                        <h3>💾 Memory Usage</h3>
                        <div class="value">${data.system.memory_usage} MB</div>
                    </div>
                    <div class="stat-card">
                        <h3>🖥 CPU Usage</h3>
                        <div class="value">${data.system.cpu_usage}%</div>
                    </div>
                    <div class="stat-card">
                        <h3>💽 Disk Usage</h3>
                        <div class="value">${data.system.disk_percent}%</div>
                    </div>
                    <div class="stat-card">
                        <h3>🕒 Uptime</h3>
                        <div class="value">${data.system.uptime}</div>
                    </div>
                `;
                
                // Update activity chart
                updateActivityChart(data.recent_activity);
                
                // Update system chart
                updateSystemChart(data.system);
                
                // Update last updated time
                document.getElementById('updateTime').textContent = new Date().toLocaleString();
                
            } catch (error) {
                console.error('Error loading stats:', error);
            }
        }
        
        async function loadUsers() {
            try {
                const response = await fetch('/api/users');
                const users = await response.json();
                
                let tableHTML = '<table><tr><th>User ID</th><th>Last Active</th><th>Files Processed</th></tr>';
                
                users.forEach(user => {
                    const lastActive = new Date(user.last_active).toLocaleDateString();
                    tableHTML += `
                        <tr>
                            <td>${user.user_id}</td>
                            <td>${lastActive}</td>
                            <td>${user.files_processed}</td>
                        </tr>
                    `;
                });
                
                tableHTML += '</table>';
                document.getElementById('usersTable').innerHTML = tableHTML;
                
            } catch (error) {
                console.error('Error loading users:', error);
            }
        }
        
        function updateActivityChart(activityData) {
            const dates = Object.keys(activityData).reverse();
            const filesData = dates.map(date => activityData[date].files_processed);
            const bytesData = dates.map(date => activityData[date].bytes_processed / (1024 * 1024)); // Convert to MB
            
            const ctx = document.getElementById('activityChart').getContext('2d');
            
            if (activityChart) {
                activityChart.destroy();
            }
            
            activityChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: dates,
                    datasets: [
                        {
                            label: 'Files Processed',
                            data: filesData,
                            borderColor: '#4CAF50',
                            backgroundColor: 'rgba(76, 175, 80, 0.1)',
                            tension: 0.4,
                            yAxisID: 'y'
                        },
                        {
                            label: 'Data Processed (MB)',
                            data: bytesData,
                            borderColor: '#2196F3',
                            backgroundColor: 'rgba(33, 150, 243, 0.1)',
                            tension: 0.4,
                            yAxisID: 'y1'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    interaction: { mode: 'index', intersect: false },
                    scales: {
                        y: {
                            type: 'linear',
                            display: true,
                            position: 'left',
                            beginAtZero: true
                        },
                        y1: {
                            type: 'linear',
                            display: true,
                            position: 'right',
                            beginAtZero: true,
                            grid: { drawOnChartArea: false }
                        }
                    }
                }
            });
        }
        
        function updateSystemChart(systemData) {
            const ctx = document.getElementById('systemChart').getContext('2d');
            
            if (systemChart) {
                systemChart.destroy();
            }
            
            systemChart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: ['Memory Used', 'Memory Free'],
                    datasets: [{
                        data: [systemData.memory_usage, 100 - systemData.memory_usage],
                        backgroundColor: ['#FF6384', '#36A2EB']
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        title: { display: true, text: 'Memory Usage' }
                    }
                }
            });
        }
        
        // Load initial data
        loadStats();
        loadUsers();
        
        // Refresh data every 10 seconds
        setInterval(() => {
            loadStats();
            loadUsers();
        }, 10000);
    </script>
</body>
</html>''')
    
    print("🌐 Starting Web Dashboard on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
