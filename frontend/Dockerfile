FROM node:20-alpine

WORKDIR /app

# Copy package config and install dependencies
COPY package.json ./
RUN npm install

# Copy application files
COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev"]
