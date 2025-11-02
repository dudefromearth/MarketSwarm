rebuild-%:
	docker compose rm -sf $*
	docker builder prune -f
	docker compose build --no-cache --pull $*
	docker compose up -d --force-recreate --no-deps $*
	docker compose logs -f $*