MJÖLNIR — LINUX PORTABILITY GUIDE

Purpose:
Run MJÖLNIR on a normal Linux machine from an arbitrary clone directory.

REQUIREMENTS

- Git
- Docker Engine
- Docker Compose
- systemd
- normal Linux user with Docker access

CHECK

git --version
docker --version
docker compose version
systemctl --version


CLONE

git clone https://github.com/marioymario/trade.git mjolnir
cd mjolnir


CONFIGURE

cp .env.example .env

Do not commit .env.


PREPARE RUNTIME DIRECTORIES

./ops/prepare_runtime.sh

This creates the local runtime directories owned by the current user, including:

- ./data
- $HOME/trade_flags

Do not create ARM, STOP, or HALT automatically.


VERIFY CONFIG

docker compose config

Paths should resolve to the current user's home directory.


BUILD AND START

CPU is the default runtime:

docker compose up -d --build

Check:

docker compose ps


CHECK LOGS

docker compose logs --tail=60 paper
docker compose logs --tail=40 trade
docker compose logs --tail=30 dashboard


OPTIONAL NVIDIA GPU

On a machine with NVIDIA Container Toolkit configured:

docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build


USER SYSTEMD

After the normal Docker startup works:

./ops/install_user_systemd.sh

The installer:

- installs the user-systemd units
- enables the stack service and heartbeat timer
- prepares required runtime directories
- does not create ARM
- does not remove STOP or HALT
- does not rewrite .env
- does not start or restart the stack automatically

Check:

systemctl --user status trade-stack.service --no-pager
systemctl --user status trade-heartbeat.timer --no-pager

For unattended startup after reboot:

loginctl show-user "$USER" -p Linger

If needed:

sudo loginctl enable-linger "$USER"


STOP

docker compose stop


CONTRIBUTING

Create a branch:

git checkout -b <name>/<change>

Review changes:

git status
git diff

Commit:

git add <files>
git commit -m "Describe the change"

Push:

git push -u origin <name>/<change>

Then open a pull request.

Do not commit:

- .env
- runtime data
- operator flags
- secrets


SAFETY

Portability work must not casually change:

- strategy behavior
- safety limits
- LONG/SHORT policy
- Event-Risk integration
- ARM/STOP/HALT semantics

ARM, STOP, and HALT remain explicit operator decisions.
