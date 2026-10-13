
#!bin/bash

docker compose up --build     
docker compose up -d --build   
docker compose logs -f api     
docker compose down            
docker compose down -v         
