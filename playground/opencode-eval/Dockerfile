FROM ghcr.io/astral-sh/uv:0.9.13-python3.12-bookworm

ENV PUID=1000 \
  PGID=1000 \
  TZ=Etc/UTC \
  PUBLIC_KEY_FILE=/authorized_keys/id_rsa.pub \
  USER_NAME=testuser \
  PASSWORD_ACCESS=false

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  openssh-server \
  tzdata \
  && rm -rf /var/lib/apt/lists/*

RUN ssh-keygen -A \
  && mkdir -p /var/run/sshd /authorized_keys

RUN groupadd -g "$PGID" "$USER_NAME" || true \
  && useradd -m -u "$PUID" -g "$PGID" -s /bin/bash "$USER_NAME" || true

RUN sed -i 's/#PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config \
  && sed -i 's/#PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config \
  && echo "PasswordAuthentication $([ "$PASSWORD_ACCESS" = "true" ] && echo "yes" || echo "no")" >> /etc/ssh/sshd_config

RUN echo '#!/bin/bash\n\
  mkdir -p "/home/$USER_NAME/.ssh"\n\
  if [ -f "$PUBLIC_KEY_FILE" ]; then\n\
  cp "$PUBLIC_KEY_FILE" "/home/$USER_NAME/.ssh/authorized_keys"\n\
  chown "$PUID:$PGID" "/home/$USER_NAME/.ssh/authorized_keys"\n\
  chmod 600 "/home/$USER_NAME/.ssh/authorized_keys"\n\
  echo "Key injected from $PUBLIC_KEY_FILE"\n\
  else\n\
  echo "Warning: No key found at $PUBLIC_KEY_FILE"\n\
  fi\n\
  chown "$PUID:$PGID" "/home/$USER_NAME/.ssh"\n\
  chmod 700 "/home/$USER_NAME/.ssh"\n\
  exec /usr/sbin/sshd -D' > /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 22

ENTRYPOINT ["/entrypoint.sh"]