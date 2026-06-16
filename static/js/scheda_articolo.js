document.addEventListener("DOMContentLoaded", function () {
    var modalElement = document.getElementById("fullscreen-carousel-modal");
    var carouselElement = document.getElementById("productCarousel");
    var uploadForm = document.getElementById("productImageUploadForm");
    var contextMenu = document.getElementById("productImageContextMenu");
    var deleteModalElement = document.getElementById("productImageDeleteModal");
    var deleteSummary = document.getElementById("productImageDeleteSummary");
    var deleteTargets = document.getElementById("productImageDeleteTargets");
    var deleteConfirmButton = document.getElementById("productImageDeleteConfirm");
    var closeButton = document.getElementById("productSheetCloseBtn");
    var productCode = document.querySelector(".product-sheet-page") ? document.querySelector(".product-sheet-page").dataset.productCode : "";
    var draggedImage = null;
    var contextImage = null;
    var deleteModal = null;
    var deleteSelection = [];

    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (element) {
        if (window.bootstrap && bootstrap.Tooltip) {
            bootstrap.Tooltip.getOrCreateInstance(element);
        }
    });

    function imagePlatform(image) {
        return image ? (image.dataset.sourcePlatform || "") : "";
    }

    function currentImageAssetId(image) {
        return image ? (image.dataset.assetId || "") : "";
    }

    function currentImageLabel(image) {
        return image ? ((image.alt || image.dataset.sourcePlatform || "immagine").trim()) : "immagine";
    }

    function getProductSheetBaseUrl() {
        return window.location.pathname.replace(/\/$/, "");
    }

    function parseJsonResponse(response) {
        return response.text().then(function (text) {
            if (!text) {
                return {};
            }
            try {
                return JSON.parse(text);
            } catch (error) {
                throw new Error(text.slice(0, 200) || "Risposta non valida dal server");
            }
        });
    }

    function platformLabel(platformKey) {
        var labels = {
            ldapp: "LDApp",
            prestashop: "Prestashop",
            poleepo: "Poleepo",
            ebay: "Ebay",
            amazon: "Amazon",
            legacy: "Legacy",
            manual: "Manuale"
        };
        return labels[platformKey] || platformKey || "Sorgente";
    }

    function sameImageFamily(imageA, imageB) {
        if (!imageA || !imageB) {
            return false;
        }
        var familyA = imageA.dataset.familyKey || imageA.dataset.assetId || imageA.src;
        var familyB = imageB.dataset.familyKey || imageB.dataset.assetId || imageB.src;
        return familyA === familyB;
    }

    function getFamilyImages(image) {
        if (!image) {
            return [];
        }
        var familyKey = image.dataset.familyKey || "";
        var images = Array.from(document.querySelectorAll("#productCarousel .carousel-item img"));
        if (familyKey) {
            return images.filter(function (candidate) {
                return (candidate.dataset.familyKey || "") === familyKey;
            });
        }
        return images.filter(function (candidate) {
            return candidate.dataset.assetId && candidate.dataset.assetId === image.dataset.assetId;
        });
    }

    function hideContextMenu() {
        if (!contextMenu) {
            return;
        }
        contextMenu.classList.remove("show");
        contextMenu.setAttribute("aria-hidden", "true");
    }

    function showContextMenu(event) {
        if (!contextMenu) {
            return;
        }
        event.preventDefault();
        contextMenu.style.left = Math.min(event.clientX, window.innerWidth - 230) + "px";
        contextMenu.style.top = Math.min(event.clientY, window.innerHeight - 190) + "px";
        contextMenu.classList.add("show");
        contextMenu.setAttribute("aria-hidden", "false");
    }

    function publishImage(image, platforms) {
        if (!image) {
            alert("Seleziona un'immagine da pubblicare.");
            return;
        }

        var assetId = currentImageAssetId(image);
        if (!assetId) {
            alert("L'immagine selezionata non ha un riferimento pubblicabile.");
            return;
        }

        return fetch(window.location.pathname + "/images/publish", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            },
            credentials: "same-origin",
            body: JSON.stringify({
                asset_id: assetId,
                platforms: platforms || []
            })
        }).then(function (response) {
            return response.json().then(function (data) {
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || "Pubblicazione non riuscita");
                }
                return data;
            });
        });
    }

    function setPrimaryImage(image) {
        if (!image) {
            alert("Seleziona un'immagine da impostare come predefinita.");
            return Promise.resolve();
        }
        var assetId = currentImageAssetId(image);
        if (!assetId) {
            alert("L'immagine selezionata non ha un riferimento valido.");
            return Promise.resolve();
        }
        return fetch(getProductSheetBaseUrl() + "/images/" + encodeURIComponent(assetId) + "/primary", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            },
            credentials: "same-origin"
        }).then(function (response) {
            return parseJsonResponse(response).then(function (data) {
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || "Impostazione default non riuscita");
                }
                return data;
            });
        });
    }

    function openDeleteModal(image) {
        if (!deleteModalElement || !deleteTargets || !deleteSummary || !deleteConfirmButton) {
            return;
        }
        var familyImages = getFamilyImages(image);
        if (!familyImages.length) {
            familyImages = image ? [image] : [];
        }
        var currentAssetId = currentImageAssetId(image);
        deleteSelection = currentAssetId ? [currentAssetId] : (familyImages[0] && familyImages[0].dataset.assetId ? [familyImages[0].dataset.assetId] : []);

        deleteSummary.textContent = familyImages.length > 1
            ? "L'immagine è condivisa tra più copie. Seleziona una o più copie da rimuovere."
            : "Seleziona la copia da rimuovere. Puoi includere anche gli altri collegamenti della stessa immagine.";

        deleteTargets.innerHTML = "";
        familyImages.forEach(function (img) {
            var assetId = img.dataset.assetId || "";
            var row = document.createElement("label");
            row.className = "form-check d-flex align-items-start gap-2 py-1";

            var checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.className = "form-check-input mt-1";
            checkbox.value = assetId;
            checkbox.checked = deleteSelection.indexOf(assetId) !== -1;
            checkbox.addEventListener("change", function () {
                if (checkbox.checked) {
                    if (deleteSelection.indexOf(assetId) === -1) {
                        deleteSelection.push(assetId);
                    }
                } else {
                    deleteSelection = deleteSelection.filter(function (value) {
                        return value !== assetId;
                    });
                }
                deleteConfirmButton.disabled = !deleteSelection.length;
            });

            var body = document.createElement("div");
            body.className = "flex-grow-1";

            var title = document.createElement("div");
            title.className = "fw-semibold";
            title.textContent = platformLabel(img.dataset.sourcePlatform) + (img.dataset.familySummary ? " - " + img.dataset.familySummary : "");

            var meta = document.createElement("div");
            meta.className = "text-muted small";
            meta.textContent = img.dataset.sourceLabel || img.dataset.sourcePlatform || "immagine";

            body.appendChild(title);
            body.appendChild(meta);
            row.appendChild(checkbox);
            row.appendChild(body);
            deleteTargets.appendChild(row);
        });

        deleteConfirmButton.disabled = !deleteSelection.length;
        deleteConfirmButton.onclick = function () {
            var selectedIds = deleteSelection.slice();
            if (!selectedIds.length) {
                alert("Seleziona almeno un'immagine da eliminare.");
                return;
            }

            deleteConfirmButton.disabled = true;
            deleteConfirmButton.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Elimino';

            fetch(getProductSheetBaseUrl() + "/images/delete", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-Requested-With": "XMLHttpRequest"
                },
                credentials: "same-origin",
                body: JSON.stringify({ asset_ids: selectedIds })
            }).then(function (response) {
                return parseJsonResponse(response).then(function (data) {
                    if (!response.ok || !data.ok) {
                        throw new Error(data.error || "Eliminazione non riuscita");
                    }
                    return data;
                });
            }).then(function () {
                deleteModal.hide();
                window.location.reload();
            }).catch(function (error) {
                alert(error.message || "Eliminazione non riuscita");
            }).finally(function () {
                deleteConfirmButton.disabled = false;
                deleteConfirmButton.innerHTML = '<i class="fa-solid fa-trash"></i> Elimina selezionate';
            });
        };

        deleteModal.show();
    }

    function reportPublishResult(image, result) {
        if (!result) {
            return;
        }

        var successTargets = [];
        var errors = [];
        Object.keys(result.results || {}).forEach(function (key) {
            var entry = result.results[key];
            if (entry && entry.ok) {
                successTargets.push(key);
            } else if (entry && entry.error) {
                errors.push(key + ": " + entry.error);
            }
        });

        var parts = [];
        if (successTargets.length) {
            parts.push("Pubblicata su: " + successTargets.join(", "));
        }
        if (errors.length) {
            parts.push("Errori: " + errors.join(" | "));
        }
        alert(parts.join("\n") || ("Pubblicazione completata per " + currentImageLabel(image)));
    }

    function selectFirstImageForPlatform(platform) {
        if (!carouselElement || !platform) {
            return;
        }
        var images = Array.from(document.querySelectorAll("#productCarousel .carousel-item img"));
        var index = images.findIndex(function (image) {
            return imagePlatform(image) === platform;
        });
        if (index >= 0) {
            bootstrap.Carousel.getOrCreateInstance(carouselElement).to(index);
        }
    }

    if (uploadForm) {
        uploadForm.addEventListener("submit", async function (event) {
            event.preventDefault();
            var input = uploadForm.querySelector('input[type="file"]');
            if (!input || !input.files || !input.files.length) {
                return;
            }

            var submit = uploadForm.querySelector('button[type="submit"]');
            var originalText = submit ? submit.innerHTML : "";
            if (submit) {
                submit.disabled = true;
                submit.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Carico';
            }

            try {
                var formData = new FormData(uploadForm);
                var response = await fetch(uploadForm.action, {
                    method: "POST",
                    body: formData,
                    credentials: "same-origin"
                });
                var data = await response.json();
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || "Upload non riuscito");
                }
                window.location.reload();
            } catch (error) {
                alert(error.message || "Upload non riuscito");
            } finally {
                if (submit) {
                    submit.disabled = false;
                    submit.innerHTML = originalText;
                }
            }
        });
    }

    document.querySelectorAll(".product-image-slot").forEach(function (slot) {
        slot.addEventListener("click", function () {
            if (slot.dataset.platformEnabled !== "1") {
                return;
            }
            selectFirstImageForPlatform(slot.dataset.platform);
        });

        slot.addEventListener("dragover", function (event) {
            if (slot.dataset.platformEnabled !== "1") {
                return;
            }
            event.preventDefault();
            slot.classList.add("product-image-slot--drop-ready");
        });

        slot.addEventListener("dragleave", function () {
            slot.classList.remove("product-image-slot--drop-ready");
        });

        slot.addEventListener("drop", function (event) {
            event.preventDefault();
            slot.classList.remove("product-image-slot--drop-ready");
            if (slot.dataset.platformEnabled !== "1" || !draggedImage) {
                return;
            }
            publishImage(draggedImage, [slot.dataset.platform]).then(function (data) {
                reportPublishResult(draggedImage, data);
                window.location.reload();
            }).catch(function (error) {
                alert(error.message || "Pubblicazione non riuscita");
            });
        });
    });

    document.addEventListener("click", hideContextMenu);
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            hideContextMenu();
        }
    });

    if (closeButton) {
        closeButton.addEventListener("click", function () {
            var fallbackUrl = closeButton.dataset.fallbackUrl || "/search/ricerca_x_descrizione";
            if (window.history.length > 1) {
                window.history.back();
            } else {
                window.location.href = fallbackUrl;
            }
        });
    }

    if (!modalElement) {
        return;
    }

    if (modalElement.parentElement !== document.body) {
        document.body.appendChild(modalElement);
    }

    modalElement.addEventListener("show.bs.modal", function () {
        document.body.classList.add("product-image-modal-open");
    });

    modalElement.addEventListener("hidden.bs.modal", function () {
        document.body.classList.remove("product-image-modal-open");
    });

    var fullscreenModal = bootstrap.Modal.getOrCreateInstance(modalElement);
    var fullscreenCarouselElement = document.getElementById("fullscreen-carousel");

    document.querySelectorAll(".product-img").forEach(function (image) {
        image.addEventListener("contextmenu", function (event) {
            contextImage = image;
            if (contextMenu) {
                contextMenu.dataset.assetId = currentImageAssetId(image);
            }
            showContextMenu(event);
        });
        image.addEventListener("dragstart", function () {
            draggedImage = image;
        });
        image.addEventListener("dragend", function () {
            draggedImage = null;
        });

        image.addEventListener("click", function () {
            var originalImages = Array.from(document.querySelectorAll("#productCarousel .carousel-item img"));
            var fullscreenImagesContainer = document.getElementById("fullscreen-carousel-images");
            var clickedIndex = Math.max(originalImages.indexOf(image), 0);

            if (!fullscreenImagesContainer || originalImages.length === 0) {
                return;
            }

            fullscreenImagesContainer.innerHTML = "";

            originalImages.forEach(function (sourceImage, index) {
                var carouselItem = document.createElement("div");
                carouselItem.classList.add("carousel-item");
                if (index === clickedIndex) {
                    carouselItem.classList.add("active");
                }

                var zoomedImage = document.createElement("img");
                zoomedImage.src = sourceImage.src;
                zoomedImage.alt = sourceImage.alt || "";
                zoomedImage.classList.add("d-block", "w-100");

                carouselItem.appendChild(zoomedImage);
                fullscreenImagesContainer.appendChild(carouselItem);
            });

            fullscreenModal.show();

            if (fullscreenCarouselElement) {
                bootstrap.Carousel.getOrCreateInstance(fullscreenCarouselElement).to(clickedIndex);
            }
        });
    });

    if (contextMenu) {
        contextMenu.querySelectorAll("button[data-action]").forEach(function (button) {
            button.addEventListener("click", function (event) {
                event.stopPropagation();
                event.preventDefault();
                hideContextMenu();
                var image = contextImage || draggedImage || document.querySelector("#productCarousel .carousel-item.active .product-img");
                if (button.dataset.action === "primary") {
                    setPrimaryImage(image).then(function () {
                        window.location.reload();
                    }).catch(function (error) {
                        alert(error.message || "Impostazione default non riuscita");
                    });
                    return;
                }
                if (button.dataset.action === "delete") {
                    openDeleteModal(image);
                }
            });
        });

        contextMenu.querySelectorAll("button[data-platform]").forEach(function (button) {
            button.addEventListener("click", function (event) {
                event.stopPropagation();
                event.preventDefault();
                hideContextMenu();
                if (button.disabled || button.dataset.platformSupported !== "1") {
                    return;
                }
                var image = contextImage || draggedImage || document.querySelector("#productCarousel .carousel-item.active .product-img");
                publishImage(image, [button.dataset.platform]).then(function (data) {
                    reportPublishResult(image, data);
                    window.location.reload();
                }).catch(function (error) {
                    alert(error.message || "Pubblicazione non riuscita");
                });
            });
        });
    }

    if (deleteModalElement) {
        if (deleteModalElement.parentElement !== document.body) {
            document.body.appendChild(deleteModalElement);
        }
        deleteModal = bootstrap.Modal.getOrCreateInstance(deleteModalElement);
        deleteModalElement.addEventListener("show.bs.modal", function () {
            document.body.classList.add("product-image-delete-modal-open");
        });
        deleteModalElement.addEventListener("hidden.bs.modal", function () {
            document.body.classList.remove("product-image-delete-modal-open");
            deleteSelection = [];
            if (deleteTargets) {
                deleteTargets.innerHTML = "";
            }
            if (deleteSummary) {
                deleteSummary.textContent = "";
            }
        });
    }
});
