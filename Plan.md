# Project Plan

## Purpose

Build the project toward an OpenWrt-style router VM that runs on an old mining rig and combines multiple WAN links into one smarter home-lab gateway.

## Target outcome

- Reuse an old mining rig as the host platform for the routing stack.
- Run a VM that acts as the main router for the network.
- Use multi-WAN load balancing and failover to combine available internet links.
- Keep the existing TP-Link research and helper scripts as migration and experimentation tools while moving toward the x86 router platform.

## Implementation direction

1. Validate the routing and policy logic with the current TP-Link-focused scripts and dry-run tooling.
2. Move the routing design into an OpenWrt-based VM for repeatable testing.
3. Use the mining-rig hardware as the long-term host for the multi-WAN router setup.
