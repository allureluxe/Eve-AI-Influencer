# Image du robot de trading.
#
#   docker build -t gold-bot -f deploy/Dockerfile .
#   docker run -d --name gold-bot --env-file .env -v $(pwd)/data:/app/data gold-bot

FROM python:3.11-slim

# Le robot raisonne entierement en UTC : les sessions de marche, le
# calendrier economique et les cles de semaine en dependent.
ENV TZ=UTC \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Aucune dependance externe : tout le robot tient dans la librairie
# standard de Python. On copie donc directement le code.
COPY gold_bot/ ./gold_bot/
COPY run_bot.py run_tests.py ./
COPY tests/ ./tests/

RUN mkdir -p /app/data \
    && useradd --create-home --uid 1000 trader \
    && chown -R trader:trader /app

USER trader

# Verification de sante : le robot doit avoir ecrit son etat recemment.
HEALTHCHECK --interval=5m --timeout=20s --start-period=2m --retries=3 \
    CMD python3 -c "import json,time,sys; \
        s=json.load(open('/app/data/state.json')); \
        sys.exit(0 if time.time()-s.get('last_cycle',0) < 900 else 1)"

ENTRYPOINT ["python3", "run_bot.py"]
CMD ["run", "--broker", "paper"]
