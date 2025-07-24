#!/bin/bash
set -e

DOMAIN="dces.app"
ADMIN_EMAIL="joanneliu0119@gmail.com"
APP_PORT=5000

# 檢查是否以 root 身份執行
if [ "$(id -u)" -ne 0 ]; then
  echo "錯誤：此腳本需要以 root 權限執行。" >&2
  echo "請嘗試使用 'sudo ./setup_nginx_ssl.sh'" >&2
  exit 1
fi

# 檢查變數是否已修改
if [ "$ADMIN_EMAIL" == "your-email@example.com" ]; then
    echo "警告：請先修改腳本中的 ADMIN_EMAIL 變數再執行！"
    exit 1
fi

echo "--- [1/4] 正在安裝 Nginx 與 Certbot ---"
apt-get update
apt-get install -y nginx python3-certbot-nginx ufw
echo "安裝完成。"
echo

echo "--- [2/4] 正在設定防火牆 (UFW) ---"
# 預設拒絕所有傳入，允許所有傳出
ufw default deny incoming
ufw default allow outgoing

# 允許必要的服務
ufw allow ssh comment 'Allow SSH connections'
ufw allow 'Nginx Full' comment 'Allow HTTP & HTTPS traffic'

# 強制啟用防火牆
yes | ufw enable
echo "防火牆已啟用並設定完成。"
ufw status
echo

echo "--- [3/4] 正在設定 Nginx 反向代理 ---"
# 建立 Nginx 設定檔
# 它會將發送到您域名的 HTTP 請求轉發到您指定的 APP_PORT
tee /etc/nginx/sites-available/${DOMAIN} > /dev/null <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# 啟用該網站設定
# -f 參數可以讓指令重複執行而不會報錯
ln -s -f /etc/nginx/sites-available/${DOMAIN} /etc/nginx/sites-enabled/

# 檢查 Nginx 設定語法並重新載入
nginx -t
systemctl reload nginx
echo "Nginx 反向代理設定完成。"
echo

echo "--- [4/4] 正在申請 SSL 憑證並自動更新設定 ---"
# --non-interactive: 非互動模式，讓腳本可以自動跑完
# --agree-tos: 自動同意服務條款
# -m: 指定 email
# --nginx: 使用 nginx 插件，它會自動修改設定檔
certbot --nginx -d ${DOMAIN} --non-interactive --agree-tos -m ${ADMIN_EMAIL}
echo "SSL 憑證申請與設定完成。"
echo

echo "================================================================="
echo "                  設定成功！"
echo "================================================================="
echo "您的網站現在應該可以透過 https://${DOMAIN} 安全地存取。"
echo "Nginx 會自動將所有流量轉發到本地的 ${APP_PORT} 端口。"
echo "SSL 憑證將會由 Certbot 自動續約。"
echo "================================================================="