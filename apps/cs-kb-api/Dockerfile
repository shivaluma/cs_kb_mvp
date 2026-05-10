FROM golang:1.25-alpine AS build

WORKDIR /src
RUN apk add --no-cache ca-certificates
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/cs-kb-api ./cmd/api

FROM alpine:3.21 AS runtime

RUN apk add --no-cache ca-certificates wget \
  && addgroup -S app \
  && adduser -S -D -H -G app app
COPY --from=build /out/cs-kb-api /usr/local/bin/cs-kb-api

USER app
ENV API_ADDR=:8080
ENV LOG_LEVEL=info
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/healthz >/dev/null || exit 1

ENTRYPOINT ["cs-kb-api"]
