FROM node:22.9.0

WORKDIR /fireant/web

COPY package*.json ./
RUN npm install

# ⭐ COPY ENV vào trước khi build
COPY .env .env

COPY . .
RUN npm run build

CMD ["npm", "run", "start"]
