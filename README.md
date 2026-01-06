# Caddy Cloudflare L4

Docker image for Caddy with Cloudflare DNS-01 ACME validation and Layer 4 (TCP/UDP) proxy support.

This repository provides a ready-to-use Caddy build with Cloudflare DNS integration, and support for [non-HTTP services via Layer 4 proxying](https://github.com/mholt/caddy-l4).


## What you get

- Cloudflare DNS-01 ACME challenge support
- Layer 4 (TCP/UDP) proxying via caddy-l4
- TLS passthrough support


## Image Registry

Images are published to GitHub Container Registry:

```
ghcr.io/eznix86/caddy-cloudflare-l4
```


## Available Tags

- `latest` – latest stable Caddy release
- `<version>` – exact Caddy version (e.g. `2.10.2`, `2.10`, `2`)
- `alpine` – latest Alpine-based image
- `<version>-alpine` – versioned Alpine images

See more at [https://github.com/eznix86/caddy-cloudflare-l4/pkgs/container/caddy-cloudflare-l4](https://github.com/eznix86/caddy-cloudflare-l4/pkgs/container/caddy-cloudflare-l4)

## Quick Start

### Pull Image

```sh
docker pull ghcr.io/eznix86/caddy-cloudflare-l4:latest
docker pull ghcr.io/eznix86/caddy-cloudflare-l4:alpine
````

## Docker Compose Example

```yaml
services:
  caddy:
    image: ghcr.io/eznix86/caddy-cloudflare-l4:latest
    restart: unless-stopped
    cap_add:
      - NET_ADMIN
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - ./site:/srv
      - caddy_data:/data
      - caddy_config:/config
    environment:
      - CLOUDFLARE_API_TOKEN=your_cloudflare_api_token

volumes:
  caddy_data:
    external: true
  caddy_config:
```

## Caddyfile Configuration

### Global Cloudflare DNS Configuration

```caddyfile
{
  acme_dns cloudflare {env.CLOUDFLARE_API_TOKEN}
}

example.com {
  root * /usr/share/caddy
  file_server
  encode gzip
}
```

### Per-Site DNS Configuration

```caddyfile
example.com {
  root * /usr/share/caddy
  file_server
  encode gzip

  tls {
    dns cloudflare {env.CLOUDFLARE_API_TOKEN}
  }
}
```


### Cloudflare IP Trust

```caddyfile
{
  acme_dns cloudflare {env.CLOUDFLARE_API_TOKEN}

  servers {
    trusted_proxies cloudflare
    client_ip_headers Cf-Connecting-Ip
  }
}

example.com {
  root * /usr/share/caddy
  file_server
}
```


## Layer 4 Proxying

### TCP Proxy Example

```caddyfile
:3306 {
  layer4 {
    proxy {
      to mysql:3306
    }
  }
}
```


### UDP Proxy Example

```caddyfile
:51820 {
  layer4 {
    proxy {
      to wireguard:51820
    }
  }
}
```

### TLS Passthrough

```caddyfile
:443 {
  layer4 {
    tls {
      passthrough
    }
    proxy {
      to backend:443
    }
  }
}
```

## Cloudflare API Token

Required permissions:

* Zone → Zone → Read
* Zone → DNS → Edit

Set the token as an environment variable:

```sh
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token
```

## Troubleshooting

DNS challenge 403 errors may require custom resolvers:

```caddyfile
tls {
  dns cloudflare {env.CLOUDFLARE_API_TOKEN}
  resolvers 1.1.1.1
}
```

Reference:
[https://github.com/caddy-dns/cloudflare#troubleshooting](https://github.com/caddy-dns/cloudflare#troubleshooting)


## Platform Support

* linux/amd64
* linux/arm64
* linux/arm/v7
* linux/ppc64le
* linux/s390x


## Building the Image

1. Fork the repository
2. Enable GitHub Actions
3. Run the build workflow
4. Image is published to your GitHub Container Registry namespace


## Contributing

Issues and pull requests are welcome.

## License

MIT License. See the LICENSE file for details.
