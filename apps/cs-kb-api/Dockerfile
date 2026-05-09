FROM golang:1.25-alpine AS build

WORKDIR /src
COPY go.mod ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /out/cs-kb-api ./cmd/api

FROM alpine:3.20

RUN adduser -D -H appuser
USER appuser
COPY --from=build /out/cs-kb-api /usr/local/bin/cs-kb-api

EXPOSE 8080
ENTRYPOINT ["cs-kb-api"]
