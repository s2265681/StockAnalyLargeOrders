module.exports = {
  apps: [
    {
      name: 'StockAnalysisLargeOrders',
      script: 'app.py',
      cwd: './backend',
      interpreter: './venv/bin/python',
      env: {
        FLASK_ENV: 'production',
        FLASK_DEBUG: '0',
        PORT: 9001
      },
      error_file: './logs/err.log',
      out_file: './logs/out.log',
      log_file: './logs/combined.log',
      time: true,
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '700M',
      min_uptime: '30s',
      max_restarts: 10,
      restart_delay: 3000,
      kill_timeout: 8000,
      env_production: {
        NODE_ENV: 'production'
      }
    }
  ]
}; 