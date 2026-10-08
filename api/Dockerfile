FROM node:20


WORKDIR /fireant/api

COPY package*.json ./

# Cài Nest CLI và dependencies
RUN npm install -g @nestjs/cli
RUN npm install

# Copy toàn bộ source vào container
COPY .env .env

COPY . .

# Build code NestJS
RUN npm run build

# Run production
CMD ["npm", "run", "start:prod"]
