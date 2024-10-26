# Gitpod have promised to support devcontainers, but it doesn't seem to work yet
# so we still need this file. This is annoying, but we should be able to delete it eventually

FROM gitpod/workspace-base

USER root

# Install Nix as root
RUN addgroup --system nixbld \
  && adduser gitpod nixbld \
  # && for i in $(seq 1 30); do useradd -ms /bin/bash nixbld$i &&  adduser nixbld$i nixbld; done \
  && mkdir -m 0755 /nix && chown gitpod /nix \
  && mkdir -p /etc/nix && echo 'sandbox = false' > /etc/nix/nix.conf
CMD /bin/bash -l

# Switch back to gitpod user
USER gitpod
ENV USER gitpod
WORKDIR /home/gitpod

RUN touch .bash_profile \
 && curl -sL https://releases.nixos.org/nix/nix-2.24.9/install | bash -s -- --no-daemon

# Configure nix
RUN echo '. /home/gitpod/.nix-profile/etc/profile.d/nix.sh' >> /home/gitpod/.bashrc
RUN mkdir -p /home/gitpod/.config/nix
RUN echo 'experimental-features = nix-command flakes' >> /home/gitpod/.config/nix/nix.conf
RUN mkdir -p /home/gitpod/.config/nixpkgs
RUN echo '{ allowUnfree = true; }' >> /home/gitpod/.config/nixpkgs/config.nix

# Install cachix, git, direnv
RUN . /home/gitpod/.nix-profile/etc/profile.d/nix.sh \
  && nix profile install nixpkgs#cachix \
  && cachix use cachix \
  && cachix use aion-physics \
  && nix profile install nixpkgs#git nixpkgs#git-lfs \
  && nix profile install nixpkgs#direnv nixpkgs#nix-direnv \
  && direnv hook bash >> /home/gitpod/.bashrc
