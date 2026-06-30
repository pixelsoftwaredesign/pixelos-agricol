# PixelOS Agricol — RootFS Image Generator
#
# Package l'intégralité du dépôt dans un système de fichiers
# en lecture seule (SquashFS ou ISO9660) prêt pour déploiement
# industriel sur les robots de la flotte.
#
# Targets :
#   all          — Détecte l'outil dispo et génère l'image appropriée
#   squashfs     — Génère une image SquashFS (.squashfs)
#   iso          — Génère une image ISO9660 (.iso)
#   hybrid       — Génère les deux formats
#   install      — Extrait l'image sur la cible (destinpath)
#   info         — Affiche les métadonnées de l'image
#   clean        — Supprime les artefacts de build
#
# Usage :
#   make all                         # auto-détection
#   make squashfs                    # SquashFS uniquement
#   make iso                         # ISO uniquement
#   make DESTDIR=/mnt/rootfs install # déploiement
#
# Variables :
#   IMAGE_NAME   — Nom de base (défaut: pixelos-agricol)
#   COMPRESSION  — Algorithme SquashFS (défaut: zstd)
#   DESTDIR      — Répertoire de déploiement (défaut: /opt/pixelos)

IMAGE_NAME ?= pixelos-agricol
COMPRESSION ?= zstd
DESTDIR    ?= /opt/pixelos
ROBOT_ROLE ?= auto

BUILD_DIR  ?= build
EXCLUDE    ?= .git __pycache__ *.pyc .DS_Store Thumbs.db *.egg-info \
             .gitignore .gitattributes .github

SQUASHFS_IMAGE := $(BUILD_DIR)/$(IMAGE_NAME).squashfs
ISO_IMAGE      := $(BUILD_DIR)/$(IMAGE_NAME).iso
ROBOT_IMAGE    := $(BUILD_DIR)/$(IMAGE_NAME)-robot-$(ROBOT_ROLE).squashfs

# Détection des outils disponibles
MKSQUASHFS   := $(shell command -v mksquashfs 2>/dev/null)
GENISOIMAGE  := $(shell command -v genisoimage 2>/dev/null)
XORRISO      := $(shell command -v xorriso 2>/dev/null)
MKHYBRID     := $(shell command -v mkhybrid 2>/dev/null)

.PHONY: all squashfs iso hybrid install info clean

all:
	@echo "=== PixelOS RootFS Builder ==="
	@echo "Detection des outils disponibles..."
	@if [ -n "$(MKSQUASHFS)" ]; then \
		echo "  + mksquashfs: $(MKSQUASHFS)"; \
		$(MAKE) squashfs; \
	elif [ -n "$(GENISOIMAGE)" ]; then \
		echo "  + genisoimage: $(GENISOIMAGE)"; \
		$(MAKE) iso; \
	elif [ -n "$(XORRISO)" ]; then \
		echo "  + xorriso: $(XORRISO)"; \
		$(MAKE) iso; \
	elif [ -n "$(MKHYBRID)" ]; then \
		echo "  + mkhybrid: $(MKHYBRID)"; \
		$(MAKE) iso; \
	else \
		echo "Aucun outil de generation d'image trouve."; \
		echo "Installez squashfs-tools (mksquashfs) ou cdrtools (genisoimage)."; \
		exit 1; \
	fi

# ─── SquashFS ──────────────────────────────────────────────
# Lecture seule, compression zstd, compatible Linux overlayfs

squashfs: $(SQUASHFS_IMAGE)

$(SQUASHFS_IMAGE): $(BUILD_DIR)
	@echo "=== Construction SquashFS ==="
	@echo "  Source:    $(CURDIR)"
	@echo "  Cible:     $@"
	@echo "  Compress:  $(COMPRESSION)"
	@EXCLUDE_OPTS=""; \
	for e in $(EXCLUDE); do \
		EXCLUDE_OPTS="$$EXCLUDE_OPTS -e $$e"; \
	done; \
	$(MKSQUASHFS) "$(CURDIR)" "$@" \
		$$EXCLUDE_OPTS \
		-comp $(COMPRESSION) \
		-b 1048576 \
		-no-recovery \
		-quiet
	@echo "  Taille: $$(du -sh $@ | cut -f1)"
	@echo "=== SquashFS creee: $@ ==="

# ─── ISO9660 ───────────────────────────────────────────────
# Bootable optionnelle, compatible UEFI+Legacy

iso: $(ISO_IMAGE)

$(ISO_IMAGE): $(BUILD_DIR)
	@echo "=== Construction ISO9660 ==="
	@echo "  Source: $(CURDIR)"
	@echo "  Cible:  $@"
	@if [ -n "$(GENISOIMAGE)" ]; then \
		genisoimage -o "$@" \
			-l -J -R -L -v -d -D -N \
			-A "PixelOS Agricol RootFS" \
			-V "PIXELOS_ROOTFS" \
			-quiet \
			$(foreach e,$(EXCLUDE),-m "$e") \
			"$(CURDIR)"; \
	elif [ -n "$(XORRISO)" ]; then \
		xorriso -as mkisofs -o "$@" \
			-l -J -R -L -V "PIXELOS_ROOTFS" \
			$(foreach e,$(EXCLUDE),-m "$e") \
			"$(CURDIR)"; \
	elif [ -n "$(MKHYBRID)" ]; then \
		mkhybrid -o "$@" \
			-l -J -R -L -v -d -D -N \
			-A "PixelOS Agricol RootFS" \
			-V "PIXELOS_ROOTFS" \
			$(foreach e,$(EXCLUDE),-m "$e") \
			"$(CURDIR)"; \
	else \
		echo "Aucun outil ISO trouve (genisoimage, xorriso, mkhybrid)"; \
		exit 1; \
	fi
	@echo "  Taille: $$(du -sh $@ | cut -f1)"
	@echo "=== ISO creee: $@ ==="

# ─── Hybride ───────────────────────────────────────────────

hybrid: squashfs iso
	@echo "=== Images generees ==="
	@ls -lh $(SQUASHFS_IMAGE) $(ISO_IMAGE)

# ─── Installation / Deploiement ───────────────────────────

install: $(SQUASHFS_IMAGE)
	@echo "=== Deploiement RootFS ==="
	@if [ ! -d "$(DESTDIR)" ]; then \
		echo "Creation de $(DESTDIR)..."; \
		mkdir -p "$(DESTDIR)"; \
	fi
	@unsquashfs -f -d "$(DESTDIR)" "$(SQUASHFS_IMAGE)" >/dev/null 2>&1 && \
		echo "  Extrait dans $(DESTDIR)" || \
		echo "  Erreur d'extraction. unsquashfs est-il installe ?"
	@echo "=== Termine ==="

# ─── Informations ──────────────────────────────────────────

info:
	@echo "=== PixelOS RootFS ==="
	@echo "  Image:       $(IMAGE_NAME)"
	@echo "  Compression: $(COMPRESSION)"
	@echo "  Excludes:    $(EXCLUDE)"
	@echo "  Build dir:   $(BUILD_DIR)"
	@echo "  Dest deploi: $(DESTDIR)"
	@echo ""
	@echo "Outils detectes:"
	@for tool in mksquashfs genisoimage xorriso mkhybrid unsquashfs; do \
		p=$$(command -v $$tool 2>/dev/null); \
		if [ -n "$$p" ]; then \
			echo "  + $$tool: $$p"; \
		else \
			echo "  - $$tool: introuvable"; \
		fi; \
	done
	@echo ""
	@echo "Arborescence source:"
	@du -sh --exclude=.git 2>/dev/null || du -sh
	@echo ""
	@echo "Targets disponibles:"
	@echo "  make all        — Auto-detect + build"
	@echo "  make squashfs   — Image SquashFS"
	@echo "  make iso        — Image ISO9660"
	@echo "  make hybrid     — Les deux formats"
	@echo "  make DESTDIR=... install — Deploiement"

# ─── Robot Image ────────────────────────────────────────────
# Image spécialisée pour déploiement sur robot avec
# vérification sécurité + modules robot pré-intégrés
#
# Usage:
#   make build-robot-image                          # auto-détection rôle
#   make build-robot-image ROBOT_ROLE=transporteur  # forcer un rôle
#   make build-robot-image ROBOT_ROLE=inspecteur COMPRESSION=gzip

.PHONY: build-robot-image verify-robot-modules

verify-robot-modules:
	@echo "=== Vérification des modules robot ==="
	@if [ "$(ROBOT_ROLE)" != "auto" ]; then \
		if [ -f "robots/$(ROBOT_ROLE).py" ] || [ -f "robots/$(ROBOT_ROLE)/__init__.py" ]; then \
			echo "  + Rôle: $(ROBOT_ROLE) — trouvé"; \
		else \
			echo "  ! Rôle $(ROBOT_ROLE) introuvable dans robots/"; \
			echo "  Rôles disponibles:"; \
			ls -d robots/*/ 2>/dev/null | sed 's/^/    - /'; \
			exit 1; \
		fi; \
	else \
		echo "  + Mode auto-détection"; \
	fi
	@for mod in core/security/robot_firewall.py core/security/boot_integrity.py robots/__init__.py robots/base.py; do \
		if [ -f "$$mod" ]; then \
			echo "  + $$mod"; \
		else \
			echo "  ! $$mod manquant"; \
			exit 1; \
		fi; \
	done
	@echo "=== Modules OK ==="

build-robot-image: verify-robot-modules $(BUILD_DIR)
	@echo "=== Construction image robot (ROBOT_ROLE=$(ROBOT_ROLE)) ==="
	@echo "  1. Génération baseline intégrité boot..."
	@cd pixelos/src && python3 -c "
from core.security.boot_integrity import create_baseline, find_project_root
root = find_project_root()
bl = create_baseline(root)
print('    Baseline:', bl.get('filepath', 'creée'))
" 2>/dev/null && echo "    Baseline OK" || echo "    Baseline ignorée (Python non dispo sur host)"
	@echo "  2. Génération règles PF robot..."
	@if command -v python3 >/dev/null 2>&1; then \
		cd pixelos/src && python3 -c "
from core.security.robot_firewall import RobotFirewall
fw = RobotFirewall(orch_ip='10.0.0.1')
print('    Règle PF:', fw.generate_rules())
" 2>/dev/null; \
	else \
		echo "    PF statique (hardware/openbsd/robot_pf.conf)"; \
	fi
	@echo "  3. Assemblage SquashFS robot..."
	@EXCLUDE_OPTS=""; \
	for e in $(EXCLUDE) hardware/installer hardware/openbsd; do \
		EXCLUDE_OPTS="$$EXCLUDE_OPTS -e $$e"; \
	done; \
	if command -v mksquashfs >/dev/null 2>&1; then \
		mksquashfs "$(CURDIR)" "$(ROBOT_IMAGE)" \
			$$EXCLUDE_OPTS \
			-comp $(COMPRESSION) \
			-b 1048576 \
			-no-recovery \
			-quiet && \
		echo "  Image robot: $(ROBOT_IMAGE)"; \
		echo "  Taille: $$(du -sh $(ROBOT_IMAGE) | cut -f1)"; \
	else \
		echo "  mksquashfs non trouvé — création d'un tar à la place..."; \
		tar czf $(ROBOT_IMAGE) \
			$$(for e in $(EXCLUDE) hardware/installer hardware/openbsd; do echo "--exclude=$$e"; done) \
			-C "$(CURDIR)" . && \
		echo "  Archive robot: $(ROBOT_IMAGE)"; \
	fi
	@echo "=== Image robot prête ==="

# ─── Clean ─────────────────────────────────────────────────

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

clean:
	rm -rf $(BUILD_DIR)
	@echo "Nettoye: $(BUILD_DIR)"
