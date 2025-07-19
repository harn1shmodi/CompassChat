FROM node:18-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Expose port 3000 for serve
EXPOSE 3000

# Use serve to serve the built files on port 3000
CMD ["npx", "serve", "-s", "dist", "-l", "3000"]
