document.addEventListener("DOMContentLoaded", function () {
    var modalElement = document.getElementById("fullscreen-carousel-modal");
    var carouselElement = document.getElementById("productCarousel");
    var uploadForm = document.getElementById("productImageUploadForm");
    var contextMenu = document.getElementById("productImageContextMenu");
    var deleteModalElement = document.getElementById("productImageDeleteModal");
    var deleteSummary = document.getElementById("productImageDeleteSummary");
    var deleteTargets = document.getElementById("productImageDeleteTargets");
    var deleteConfirmButton = document.getElementById("productImageDeleteConfirm");
    var publicationModalElement = document.getElementById("productPublicationModal");
    var publicationTitle = document.getElementById("productPublicationTitle");
    var publicationSubtitle = document.getElementById("productPublicationSubtitle");
    var publicationFields = document.getElementById("productPublicationFields");
    var publicationSaveButton = document.getElementById("productPublicationSave");
    var publicationPublishButton = document.getElementById("productPublicationPublish");
    var publicationCopyPanel = document.getElementById("productPublicationCopyPanel");
    var publicationCopySearch = document.getElementById("productPublicationCopySearch");
    var publicationCopySearchButton = document.getElementById("productPublicationCopySearchBtn");
    var publicationCopyResults = document.getElementById("productPublicationCopyResults");
    var imageCopyOpenButton = document.getElementById("productImageCopyOpen");
    var imageCopyModalElement = document.getElementById("productImageCopyModal");
    var imageCopySearch = document.getElementById("productImageCopySearch");
    var imageCopySearchButton = document.getElementById("productImageCopySearchBtn");
    var imageCopyResults = document.getElementById("productImageCopyResults");
    var imageCopyConfirmButton = document.getElementById("productImageCopyConfirm");
    var closeButton = document.getElementById("productSheetCloseBtn");
    var productCode = document.querySelector(".product-sheet-page") ? document.querySelector(".product-sheet-page").dataset.productCode : "";
    var draggedImage = null;
    var contextImage = null;
    var deleteModal = null;
    var deleteSelection = [];
    var publicationModal = null;
    var imageCopyModal = null;
    var publicationPlatform = "";
    var publicationMode = "publish";
    var imageCopySelection = [];

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
            return parseJsonResponse(response).then(function (data) {
                if (!response.ok || !data.ok) {
                    var errorParts = [];
                    if (data && data.error) {
                        errorParts.push(data.error);
                    }
                    if (data && data.results) {
                        Object.keys(data.results).forEach(function (key) {
                            var entry = data.results[key];
                            if (entry && entry.error) {
                                errorParts.push(platformLabel(key) + ": " + entry.error);
                            }
                        });
                    }
                    throw new Error(errorParts.join(" | ") || "Pubblicazione non riuscita");
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
                errors.push(platformLabel(key) + ": " + entry.error);
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

    function imageCopyCandidatesUrl(query) {
        return getProductSheetBaseUrl() + "/images/copy-candidates?q=" + encodeURIComponent(query || "");
    }

    function imageCopyUrl() {
        return getProductSheetBaseUrl() + "/images/copy";
    }

    function localDataCopyUrl() {
        return getProductSheetBaseUrl() + "/copy-local-data";
    }

    function setImageCopySelected(assetId, selected) {
        assetId = String(assetId || "");
        if (!assetId) {
            return;
        }
        if (selected) {
            if (imageCopySelection.indexOf(assetId) === -1) {
                imageCopySelection.push(assetId);
            }
        } else {
            imageCopySelection = imageCopySelection.filter(function (value) {
                return value !== assetId;
            });
        }
        updateImageCopyConfirmState();
    }

    function updateImageCopyConfirmState() {
        if (!imageCopyConfirmButton) {
            return;
        }
        imageCopyConfirmButton.disabled = !imageCopySelection.length;
        imageCopyConfirmButton.innerHTML = imageCopySelection.length
            ? '<i class="fa-solid fa-copy"></i> Copia selezionate (' + imageCopySelection.length + ')'
            : '<i class="fa-solid fa-copy"></i> Copia selezionate';
    }

    function resetImageCopyState() {
        imageCopySelection = [];
        updateImageCopyConfirmState();
    }

    function renderImageCopyResults(items) {
        if (!imageCopyResults) {
            return;
        }
        resetImageCopyState();
        imageCopyResults.innerHTML = "";
        if (!items || !items.length) {
            imageCopyResults.innerHTML = '<div class="text-muted">Nessuna immagine trovata.</div>';
            return;
        }
        items.forEach(function (item) {
            var wrapper = document.createElement("div");
            wrapper.className = "product-image-copy-result";

            var title = document.createElement("div");
            title.className = "fw-semibold mb-1";
            title.textContent = item.cod_art + " - " + (item.descrizione || "");
            wrapper.appendChild(title);

            if (item.descrizione_aggiuntiva) {
                var subtitle = document.createElement("div");
                subtitle.className = "text-muted small mb-2";
                subtitle.textContent = item.descrizione_aggiuntiva;
                wrapper.appendChild(subtitle);
            }

            var toolbar = document.createElement("div");
            toolbar.className = "d-flex flex-wrap gap-2 mb-2";

            var selectAll = document.createElement("button");
            selectAll.type = "button";
            selectAll.className = "btn btn-sm btn-outline-secondary";
            selectAll.textContent = "Seleziona tutte";

            var clearAll = document.createElement("button");
            clearAll.type = "button";
            clearAll.className = "btn btn-sm btn-outline-secondary";
            clearAll.textContent = "Deseleziona tutte";

            var grid = document.createElement("div");
            grid.className = "product-image-copy-grid";
            var itemCheckboxes = [];
            (item.images || []).forEach(function (image) {
                if (!image.id) {
                    return;
                }
                var label = document.createElement("label");
                label.className = "product-image-copy-thumb";
                label.dataset.assetId = image.id;

                var img = document.createElement("img");
                img.src = image.url;
                img.alt = item.cod_art;
                label.appendChild(img);

                var row = document.createElement("span");
                row.className = "d-flex align-items-start gap-2";

                var checkbox = document.createElement("input");
                checkbox.type = "checkbox";
                checkbox.className = "form-check-input mt-1";
                checkbox.value = image.id;
                checkbox.addEventListener("change", function () {
                    setImageCopySelected(image.id, checkbox.checked);
                });
                itemCheckboxes.push(checkbox);

                var meta = document.createElement("span");
                meta.className = "small text-muted";
                meta.textContent = platformLabel(image.source_platform);

                row.appendChild(checkbox);
                row.appendChild(meta);
                label.appendChild(row);
                grid.appendChild(label);
            });
            selectAll.addEventListener("click", function () {
                itemCheckboxes.forEach(function (checkbox) {
                    checkbox.checked = true;
                    setImageCopySelected(checkbox.value, true);
                });
            });
            clearAll.addEventListener("click", function () {
                itemCheckboxes.forEach(function (checkbox) {
                    checkbox.checked = false;
                    setImageCopySelected(checkbox.value, false);
                });
            });
            toolbar.appendChild(selectAll);
            toolbar.appendChild(clearAll);
            wrapper.appendChild(toolbar);
            wrapper.appendChild(grid);
            imageCopyResults.appendChild(wrapper);
        });
    }

    function searchImagesToCopy() {
        if (!imageCopySearch || !imageCopyResults) {
            return;
        }
        var query = imageCopySearch.value.trim();
        if (query.length < 2) {
            imageCopyResults.innerHTML = '<div class="text-muted">Inserisci almeno 2 caratteri.</div>';
            return;
        }
        imageCopyResults.innerHTML = '<div class="text-muted">Cerco immagini...</div>';
        fetch(imageCopyCandidatesUrl(query), {
            method: "GET",
            headers: { "X-Requested-With": "XMLHttpRequest" },
            credentials: "same-origin"
        }).then(function (response) {
            return parseJsonResponse(response).then(function (data) {
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || "Ricerca immagini non riuscita");
                }
                return data.items || [];
            });
        }).then(renderImageCopyResults).catch(function (error) {
            imageCopyResults.innerHTML = '<div class="alert alert-danger mb-0">' + (error.message || "Ricerca immagini non riuscita") + '</div>';
        });
    }

    function copySelectedImages() {
        if (!imageCopySelection.length || !imageCopyConfirmButton) {
            alert("Seleziona almeno una immagine da copiare.");
            return;
        }
        var originalHtml = imageCopyConfirmButton.innerHTML;
        imageCopyConfirmButton.disabled = true;
        imageCopyConfirmButton.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Copio';
        fetch(imageCopyUrl(), {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            },
            credentials: "same-origin",
            body: JSON.stringify({ asset_ids: imageCopySelection.slice() })
        }).then(function (response) {
            return parseJsonResponse(response).then(function (data) {
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || "Copia immagine non riuscita");
                }
                return data;
            });
        }).then(function () {
            window.location.reload();
        }).catch(function (error) {
            alert(error.message || "Copia immagine non riuscita");
            imageCopyConfirmButton.disabled = false;
            imageCopyConfirmButton.innerHTML = originalHtml;
        });
    }

    function publicationDraftUrl(platform) {
        return getProductSheetBaseUrl() + "/publish/" + encodeURIComponent(platform) + "/draft";
    }

    function publicationPublishUrl(platform) {
        return getProductSheetBaseUrl() + "/publish/" + encodeURIComponent(platform);
    }

    function publicationUpdateUrl(platform) {
        return getProductSheetBaseUrl() + "/publish/" + encodeURIComponent(platform) + "/update";
    }

    function publicationCopyCandidatesUrl(platform, query) {
        return getProductSheetBaseUrl() + "/publish/" + encodeURIComponent(platform) + "/copy-candidates?q=" + encodeURIComponent(query || "");
    }

    function publicationCopyValuesUrl(platform, sourceCodArt) {
        return getProductSheetBaseUrl() + "/publish/" + encodeURIComponent(platform) + "/copy-values?source_cod_art=" + encodeURIComponent(sourceCodArt || "");
    }

    function copyLocalDataFromSource(sourceCodArt, assetIds) {
        return fetch(localDataCopyUrl(), {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            },
            credentials: "same-origin",
            body: JSON.stringify({
                source_cod_art: sourceCodArt,
                copy_sheet: true,
                overwrite_sheet: false,
                copy_barcodes: true,
                overwrite_barcodes: false,
                asset_ids: assetIds || []
            })
        }).then(function (response) {
            return parseJsonResponse(response).then(function (data) {
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || "Copia dati locali non riuscita");
                }
                return data;
            });
        });
    }

    function selectedPublicationCopyImageIds(button) {
        var row = button.closest(".product-publication-copy-result");
        if (!row) {
            return [];
        }
        return Array.from(row.querySelectorAll(".product-publication-copy-image-check:checked")).map(function (checkbox) {
            return checkbox.value;
        });
    }

    function publicationFieldInput(name, language) {
        return publicationFields.querySelector(
            "[data-field-name='" + CSS.escape(name) + "'] .form-control[data-language='" + CSS.escape(language || "") + "']"
        );
    }

    function setPublicationSourceValue(input, sourceLabel, sourceValue) {
        if (!input) {
            return false;
        }
        var wrapper = input.closest("[data-field-name]");
        if (!wrapper) {
            return false;
        }
        var existing = wrapper.querySelector(".product-publication-source-value");
        if (existing) {
            existing.remove();
        }
        var sourceBox = document.createElement("div");
        sourceBox.className = "product-publication-source-value";
        var currentValue = input.value || "";
        var sourceText = String(sourceValue || "").trim();
        var currentText = String(currentValue || "").trim();
        sourceBox.classList.add(sourceText === currentText ? "is-same" : "is-different");

        var title = document.createElement("div");
        title.className = "fw-semibold mb-1";
        title.textContent = sourceLabel;

        var sourceLine = document.createElement("div");
        sourceLine.className = "mb-1";
        sourceLine.innerHTML = '<span class="text-muted">Valore origine:</span> <span class="fw-semibold"></span>';
        sourceLine.querySelector("span.fw-semibold").textContent = sourceValue || "";

        var currentLine = document.createElement("div");
        currentLine.className = "mb-2";
        currentLine.innerHTML = '<span class="text-muted">Valore corrente:</span> <span></span>';
        currentLine.querySelector("span:last-child").textContent = currentValue || "";

        var actions = document.createElement("div");
        actions.className = "d-flex flex-wrap gap-2";

        var useSource = document.createElement("button");
        useSource.type = "button";
        useSource.className = "btn btn-sm btn-outline-primary";
        useSource.textContent = "Usa origine";
        useSource.addEventListener("click", function () {
            input.value = sourceValue || "";
            currentLine.querySelector("span:last-child").textContent = input.value || "";
        });

        var keepCurrent = document.createElement("button");
        keepCurrent.type = "button";
        keepCurrent.className = "btn btn-sm btn-outline-secondary";
        keepCurrent.textContent = "Mantieni corrente";
        keepCurrent.addEventListener("click", function () {
            input.value = currentValue || "";
            currentLine.querySelector("span:last-child").textContent = input.value || "";
        });

        actions.appendChild(useSource);
        actions.appendChild(keepCurrent);
        sourceBox.appendChild(title);
        sourceBox.appendChild(sourceLine);
        sourceBox.appendChild(currentLine);
        sourceBox.appendChild(actions);
        var label = wrapper.querySelector(".form-label");
        if (label && label.parentElement === wrapper) {
            wrapper.insertBefore(sourceBox, label.nextSibling);
        } else {
            wrapper.insertBefore(sourceBox, wrapper.firstChild);
        }
        return sourceBox;
    }

    function renderComparisonSummary(container, sourceLabel, comparisons) {
        var existing = container.querySelector(".product-publication-comparison-summary");
        if (existing) {
            existing.remove();
        }
        var summary = document.createElement("div");
        summary.className = "product-publication-comparison-summary mt-2";

        var title = document.createElement("div");
        title.className = "fw-semibold mb-2";
        title.textContent = sourceLabel + " - confronto valori";
        summary.appendChild(title);

        comparisons.forEach(function (entry) {
            var row = document.createElement("div");
            row.className = "product-publication-comparison-row";

            var name = document.createElement("div");
            name.className = "fw-semibold";
            name.textContent = entry.label || entry.name;

            var origin = document.createElement("div");
            origin.className = "small";
            origin.innerHTML = '<span class="text-muted">Origine:</span> <span class="fw-semibold"></span>';
            origin.querySelector("span.fw-semibold").textContent = entry.sourceValue || "";

            var current = document.createElement("div");
            current.className = "small mb-2";
            current.innerHTML = '<span class="text-muted">Corrente:</span> <span></span>';
            current.querySelector("span:last-child").textContent = entry.currentValue || "";

            var actions = document.createElement("div");
            actions.className = "d-flex flex-wrap gap-2";
            var useSource = document.createElement("button");
            useSource.type = "button";
            useSource.className = "btn btn-sm btn-outline-primary";
            useSource.textContent = "Usa origine";
            useSource.addEventListener("click", function () {
                entry.input.value = entry.sourceValue || "";
                current.querySelector("span:last-child").textContent = entry.input.value || "";
            });
            var keepCurrent = document.createElement("button");
            keepCurrent.type = "button";
            keepCurrent.className = "btn btn-sm btn-outline-secondary";
            keepCurrent.textContent = "Mantieni corrente";
            keepCurrent.addEventListener("click", function () {
                entry.input.value = entry.currentValue || "";
                current.querySelector("span:last-child").textContent = entry.input.value || "";
            });
            actions.appendChild(useSource);
            actions.appendChild(keepCurrent);

            row.appendChild(name);
            row.appendChild(origin);
            row.appendChild(current);
            row.appendChild(actions);
            summary.appendChild(row);
        });

        container.appendChild(summary);
    }

    function resetPublicationCopyPanel() {
        if (publicationCopySearch) {
            publicationCopySearch.value = "";
        }
        if (publicationCopyResults) {
            publicationCopyResults.innerHTML = '<div class="text-muted small">Cerca un prodotto origine.</div>';
        }
    }

    function renderPublicationCopyResults(items) {
        if (!publicationCopyResults) {
            return;
        }
        publicationCopyResults.innerHTML = "";
        if (!items || !items.length) {
            publicationCopyResults.innerHTML = '<div class="text-muted small">Nessun prodotto origine valido trovato.</div>';
            return;
        }
        items.forEach(function (item) {
            var row = document.createElement("div");
            row.className = "product-publication-copy-result";

            var body = document.createElement("div");
            body.className = "min-w-0";
            var title = document.createElement("div");
            title.className = "fw-semibold";
            title.textContent = item.cod_art + " - " + (item.descrizione || "");
            body.appendChild(title);
            if (item.descrizione_aggiuntiva) {
                var subtitle = document.createElement("div");
                subtitle.className = "text-muted small";
                subtitle.textContent = item.descrizione_aggiuntiva;
                body.appendChild(subtitle);
            }
            var meta = document.createElement("div");
            meta.className = "text-muted small";
            meta.textContent = "Poleepo " + (item.external_id || "-");
            body.appendChild(meta);

            var localCopy = item.local_copy || {};
            var barcodes = localCopy.barcodes || [];
            if (barcodes.length) {
                var barcodeMeta = document.createElement("div");
                barcodeMeta.className = "text-muted small";
                barcodeMeta.textContent = "Barcode: " + barcodes.join(", ");
                body.appendChild(barcodeMeta);
            } else {
                var noBarcodeMeta = document.createElement("div");
                noBarcodeMeta.className = "text-muted small";
                noBarcodeMeta.textContent = "Barcode: assente";
                body.appendChild(noBarcodeMeta);
            }

            var images = localCopy.images || [];
            if (images.length) {
                var imagesTitle = document.createElement("div");
                imagesTitle.className = "small fw-semibold mt-2 mb-1";
                imagesTitle.textContent = "Immagini da copiare";
                body.appendChild(imagesTitle);

                var imageToolbar = document.createElement("div");
                imageToolbar.className = "d-flex flex-wrap gap-2 mb-2";
                var selectImages = document.createElement("button");
                selectImages.type = "button";
                selectImages.className = "btn btn-sm btn-outline-secondary";
                selectImages.textContent = "Seleziona tutte";
                var clearImages = document.createElement("button");
                clearImages.type = "button";
                clearImages.className = "btn btn-sm btn-outline-secondary";
                clearImages.textContent = "Deseleziona tutte";
                imageToolbar.appendChild(selectImages);
                imageToolbar.appendChild(clearImages);
                body.appendChild(imageToolbar);

                var imageGrid = document.createElement("div");
                imageGrid.className = "product-image-copy-grid";
                images.forEach(function (image) {
                    if (!image.id) {
                        return;
                    }
                    var label = document.createElement("label");
                    label.className = "product-image-copy-thumb";
                    var img = document.createElement("img");
                    img.src = image.url;
                    img.alt = item.cod_art;
                    label.appendChild(img);

                    var checkRow = document.createElement("span");
                    checkRow.className = "d-flex align-items-start gap-2";
                    var checkbox = document.createElement("input");
                    checkbox.type = "checkbox";
                    checkbox.className = "form-check-input mt-1 product-publication-copy-image-check";
                    checkbox.value = image.id;
                    checkbox.checked = true;
                    var source = document.createElement("span");
                    source.className = "small text-muted";
                    source.textContent = platformLabel(image.source_platform);
                    checkRow.appendChild(checkbox);
                    checkRow.appendChild(source);
                    label.appendChild(checkRow);
                    imageGrid.appendChild(label);
                });
                selectImages.addEventListener("click", function () {
                    imageGrid.querySelectorAll(".product-publication-copy-image-check").forEach(function (checkbox) {
                        checkbox.checked = true;
                    });
                });
                clearImages.addEventListener("click", function () {
                    imageGrid.querySelectorAll(".product-publication-copy-image-check").forEach(function (checkbox) {
                        checkbox.checked = false;
                    });
                });
                body.appendChild(imageGrid);
            } else {
                var noImages = document.createElement("div");
                noImages.className = "text-muted small mt-2";
                noImages.textContent = "Nessuna immagine moderna copiabile.";
                body.appendChild(noImages);
            }

            var button = document.createElement("button");
            button.type = "button";
            button.className = "btn btn-sm btn-outline-primary";
            button.innerHTML = '<i class="fa-solid fa-code-compare"></i> Confronta valori';
            button.addEventListener("click", function () {
                applyPublicationCopyValues(button, item.cod_art);
            });

            var localButton = document.createElement("button");
            localButton.type = "button";
            localButton.className = "btn btn-sm btn-outline-secondary";
            localButton.innerHTML = '<i class="fa-solid fa-copy"></i> Copia dati locali';
            localButton.addEventListener("click", function () {
                copySelectedLocalData(localButton, item.cod_art);
            });

            row.appendChild(body);
            var actions = document.createElement("div");
            actions.className = "d-grid gap-2";
            actions.appendChild(button);
            actions.appendChild(localButton);
            row.appendChild(actions);
            publicationCopyResults.appendChild(row);
        });
    }

    function copySelectedLocalData(button, sourceCodArt) {
        var originalHtml = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Copio';
        copyLocalDataFromSource(sourceCodArt, selectedPublicationCopyImageIds(button)).then(function (localData) {
            var sheet = localData.results && localData.results.sheet;
            var images = localData.results && localData.results.images;
            var barcodes = localData.results && localData.results.barcodes;
            var messages = [];
            if (sheet && sheet.status === "copied") {
                messages.push("scheda tecnica");
            }
            if (images && images.copied) {
                messages.push(images.copied + " immagini");
            }
            if (barcodes && barcodes.copied) {
                messages.push(barcodes.copied + " barcode");
            }
            var notice = document.createElement("div");
            notice.className = messages.length ? "alert alert-success py-2 mt-2 mb-0" : "alert alert-info py-2 mt-2 mb-0";
            notice.textContent = messages.length
                ? "Copiati da " + sourceCodArt + ": " + messages.join(", ") + "."
                : "Nessun dato locale copiato: il target ha gia' dati o l'origine non contiene elementi copiabili.";
            publicationCopyResults.prepend(notice);
        }).catch(function (error) {
            alert(error.message || "Copia dati locali non riuscita");
        }).finally(function () {
            button.disabled = false;
            button.innerHTML = originalHtml;
        });
    }

    function searchPublicationCopyValues() {
        if (!publicationCopySearch || !publicationCopyResults || publicationPlatform !== "poleepo") {
            return;
        }
        var query = publicationCopySearch.value.trim();
        if (query.length < 2) {
            publicationCopyResults.innerHTML = '<div class="text-muted small">Inserisci almeno 2 caratteri.</div>';
            return;
        }
        publicationCopyResults.innerHTML = '<div class="text-muted small">Cerco prodotti origine...</div>';
        fetch(publicationCopyCandidatesUrl(publicationPlatform, query), {
            method: "GET",
            headers: { "X-Requested-With": "XMLHttpRequest" },
            credentials: "same-origin"
        }).then(function (response) {
            return parseJsonResponse(response).then(function (data) {
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || "Ricerca prodotto origine non riuscita");
                }
                return data.items || [];
            });
        }).then(renderPublicationCopyResults).catch(function (error) {
            publicationCopyResults.innerHTML = '<div class="alert alert-danger mb-0">' + (error.message || "Ricerca prodotto origine non riuscita") + '</div>';
        });
    }

    function applyPublicationCopyValues(button, sourceCodArt) {
        var originalHtml = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Copio';
        fetch(publicationCopyValuesUrl(publicationPlatform, sourceCodArt), {
            method: "GET",
            headers: { "X-Requested-With": "XMLHttpRequest" },
            credentials: "same-origin"
        }).then(function (response) {
            return parseJsonResponse(response).then(function (data) {
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || "Copia valori non riuscita");
                }
                return data;
            });
        }).then(function (data) {
            var sourceLabel = "Origine " + ((data.source && data.source.cod_art) || sourceCodArt);
            var inserted = 0;
            var firstBox = null;
            var firstWrapper = null;
            var comparisons = [];
            (data.fields || []).forEach(function (field) {
                var input = publicationFieldInput(field.name, field.language || "");
                if (!input || input.dataset.readonly === "1") {
                    return;
                }
                var box = setPublicationSourceValue(input, sourceLabel, field.value || "");
                if (box) {
                    inserted += 1;
                    if (!firstBox) {
                        firstBox = box;
                        firstWrapper = input.closest("[data-field-name]");
                    }
                    comparisons.push({
                        name: field.name,
                        label: field.label,
                        input: input,
                        sourceValue: field.value || "",
                        currentValue: input.value || ""
                    });
                }
            });
            var resultRow = button.closest(".product-publication-copy-result");
            if (resultRow && comparisons.length) {
                renderComparisonSummary(resultRow.querySelector(".min-w-0") || resultRow, sourceLabel, comparisons);
            }
            var notice = document.createElement("div");
            notice.className = inserted ? "alert alert-info py-2 mt-2 mb-0" : "alert alert-warning py-2 mt-2 mb-0";
            notice.textContent = inserted
                ? "Confronto caricato su " + inserted + " campi. Scegli campo per campo cosa mantenere."
                : "Nessun campo confrontabile trovato nella modale corrente.";
            publicationCopyResults.prepend(notice);
            if (firstBox && firstWrapper && publicationFields) {
                publicationFields.scrollTo({
                    top: Math.max(firstWrapper.offsetTop - publicationFields.offsetTop - 8, 0),
                    behavior: "smooth"
                });
            }
        }).catch(function (error) {
            alert(error.message || "Copia valori non riuscita");
        }).finally(function () {
            button.disabled = false;
            button.innerHTML = originalHtml;
        });
    }

    function renderPublicationField(field) {
        var wrapper = document.createElement("div");
        wrapper.className = "product-publication-field" + (field.missing ? " is-missing" : "");
        wrapper.dataset.fieldName = field.name;
        wrapper.dataset.language = field.language || "";

        var label = document.createElement("label");
        label.className = "form-label d-flex justify-content-between gap-2";
        label.htmlFor = "publish-field-" + field.name;
        label.innerHTML = "<span>" + field.label + (field.required ? " *" : "") + "</span><span class=\"text-muted small\">" + field.source + "</span>";

        var input;
        var filterInput = null;
        if (field.type === "readonly" || field.readonly) {
            input = document.createElement("textarea");
            input.rows = 2;
            input.readOnly = true;
        } else if (field.options && field.options.length) {
            if (field.options.length > 20) {
                filterInput = document.createElement("input");
                filterInput.type = "search";
                filterInput.className = "form-control form-control-sm mb-2";
                filterInput.placeholder = "Filtra elenco...";
            }
            input = document.createElement("select");
            if (!field.required) {
                var emptyOption = document.createElement("option");
                emptyOption.value = "";
                emptyOption.textContent = "Nessuna selezione";
                input.appendChild(emptyOption);
            } else {
                var placeholderOption = document.createElement("option");
                placeholderOption.value = "";
                placeholderOption.textContent = "Seleziona...";
                input.appendChild(placeholderOption);
            }
            field.options.forEach(function (optionData) {
                var option = document.createElement("option");
                option.value = optionData.value;
                option.textContent = optionData.label;
                input.appendChild(option);
            });
            if (filterInput) {
                filterInput.addEventListener("input", function () {
                    var query = filterInput.value.trim().toLowerCase();
                    Array.from(input.options).forEach(function (option, index) {
                        if (index === 0) {
                            option.hidden = false;
                            return;
                        }
                        option.hidden = query && option.textContent.toLowerCase().indexOf(query) === -1;
                    });
                });
            }
        } else if (field.type === "textarea") {
            input = document.createElement("textarea");
            input.rows = 4;
        } else if (field.type === "bool") {
            input = document.createElement("select");
            [
                { value: "1", label: "Si" },
                { value: "0", label: "No" }
            ].forEach(function (optionData) {
                var option = document.createElement("option");
                option.value = optionData.value;
                option.textContent = optionData.label;
                input.appendChild(option);
            });
        } else {
            input = document.createElement("input");
            input.type = field.type === "decimal" || field.type === "integer" ? "number" : "text";
            if (field.type === "decimal") {
                input.step = "0.01";
            }
            if (field.type === "integer") {
                input.step = "1";
            }
        }
        input.id = "publish-field-" + field.name;
        input.className = "form-control";
        input.value = field.value || "";
        input.dataset.fieldName = field.name;
        input.dataset.language = field.language || "";
        if (field.readonly) {
            input.dataset.readonly = "1";
            input.classList.add("bg-light");
        }
        if (field.required) {
            input.required = true;
        }

        var help = document.createElement("div");
        help.className = "form-text";
        if (field.options_error) {
            help.textContent = "Lista valori non disponibile: " + field.options_error;
        } else if (field.help) {
            help.textContent = field.help;
        } else {
            help.textContent = field.saved
                ? "Valore salvato nella bozza piattaforma."
                : "Valore proposto dal mapping LDApp.";
        }

        wrapper.appendChild(label);
        if (filterInput) {
            wrapper.appendChild(filterInput);
        }
        wrapper.appendChild(input);
        wrapper.appendChild(help);
        return wrapper;
    }

    function renderPublicationDraft(draft) {
        if (!publicationFields) {
            return;
        }
        publicationFields.innerHTML = "";
        if (publicationTitle) {
            publicationTitle.textContent = (publicationMode === "update" ? "Modifica su " : "Pubblica su ") + draft.label;
        }
        if (publicationSubtitle) {
            publicationSubtitle.textContent = "Articolo " + draft.cod_art + " - " + draft.fields.length + " campi";
        }
        if (draft.missing_required && draft.missing_required.length) {
            var alertBox = document.createElement("div");
            alertBox.className = "alert alert-warning small mb-0";
            alertBox.textContent = "Completa i campi obbligatori mancanti prima della pubblicazione reale.";
            publicationFields.appendChild(alertBox);
        }
        if (publicationPublishButton) {
            var supportedPublishPlatforms = ["prestashop", "poleepo"];
            var canPublishPlatform = supportedPublishPlatforms.indexOf(draft.platform) !== -1;
            publicationPublishButton.disabled = Boolean(draft.missing_required && draft.missing_required.length) || !canPublishPlatform;
            publicationPublishButton.innerHTML = canPublishPlatform
                ? '<i class="fa-solid fa-cloud-arrow-up"></i> ' + (publicationMode === "update" ? "Aggiorna su " : "Pubblica su ") + draft.label
                : '<i class="fa-solid fa-cloud-arrow-up"></i> Pubblicazione non disponibile';
        }
        if (publicationCopyPanel) {
            if (publicationMode === "update" && draft.platform === "poleepo") {
                publicationCopyPanel.classList.remove("d-none");
            } else {
                publicationCopyPanel.classList.add("d-none");
                resetPublicationCopyPanel();
            }
        }
        draft.fields.forEach(function (field) {
            publicationFields.appendChild(renderPublicationField(field));
        });
    }

    function collectPublicationFields() {
        return Array.from(publicationFields.querySelectorAll("[data-field-name] .form-control")).map(function (input) {
            if (input.dataset.readonly === "1") {
                return null;
            }
            return {
                name: input.dataset.fieldName,
                language: input.dataset.language || "",
                value: input.value
            };
        }).filter(Boolean);
    }

    function openPublicationModal(platform, mode) {
        if (!publicationModal || !publicationFields) {
            return;
        }
        publicationPlatform = platform;
        publicationMode = mode || "publish";
        publicationFields.innerHTML = "<div class=\"text-muted\">Caricamento campi...</div>";
        if (publicationSaveButton) {
            publicationSaveButton.disabled = true;
        }
        if (publicationPublishButton) {
            publicationPublishButton.disabled = true;
        }
        publicationModal.show();
        fetch(publicationDraftUrl(platform), {
            method: "GET",
            headers: { "X-Requested-With": "XMLHttpRequest" },
            credentials: "same-origin"
        }).then(function (response) {
            return parseJsonResponse(response).then(function (data) {
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || "Bozza pubblicazione non disponibile");
                }
                return data.draft;
            });
        }).then(function (draft) {
            renderPublicationDraft(draft);
            if (publicationSaveButton) {
                publicationSaveButton.disabled = false;
            }
        }).catch(function (error) {
            publicationFields.innerHTML = "<div class=\"alert alert-danger mb-0\">" + (error.message || "Errore caricamento bozza") + "</div>";
        });
    }

    function savePublicationDraft() {
        if (!publicationPlatform || !publicationSaveButton) {
            return;
        }
        publicationSaveButton.disabled = true;
        publicationSaveButton.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Salvo';
        fetch(publicationDraftUrl(publicationPlatform), {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            },
            credentials: "same-origin",
            body: JSON.stringify({ fields: collectPublicationFields() })
        }).then(function (response) {
            return parseJsonResponse(response).then(function (data) {
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || "Salvataggio bozza non riuscito");
                }
                return data.draft;
            });
        }).then(function (draft) {
            renderPublicationDraft(draft);
            alert("Bozza salvata in LDApp. Nessun prodotto remoto e' stato creato.");
        }).catch(function (error) {
            alert(error.message || "Salvataggio bozza non riuscito");
        }).finally(function () {
            publicationSaveButton.disabled = false;
            publicationSaveButton.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Salva bozza';
        });
    }

    function publishProductDraft() {
        if (!publicationPlatform || !publicationPublishButton) {
            return;
        }
        var isUpdate = publicationMode === "update";
        var confirmText = isUpdate
            ? "Aggiornare ora il prodotto sulla piattaforma selezionata?"
            : "Pubblicare ora il prodotto sulla piattaforma selezionata?";
        if (!window.confirm(confirmText)) {
            return;
        }
        publicationPublishButton.disabled = true;
        publicationPublishButton.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> ' + (isUpdate ? "Aggiorno" : "Pubblico");
        fetch(isUpdate ? publicationUpdateUrl(publicationPlatform) : publicationPublishUrl(publicationPlatform), {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            },
            credentials: "same-origin",
            body: JSON.stringify({ fields: collectPublicationFields() })
        }).then(function (response) {
            return parseJsonResponse(response).then(function (data) {
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || "Pubblicazione prodotto non riuscita");
                }
                return data;
            });
        }).then(function (data) {
            var result = data.result || {};
            alert((isUpdate ? "Prodotto aggiornato. ID esterno: " : "Prodotto pubblicato. ID esterno: ") + (result.external_id || "-"));
            window.location.reload();
        }).catch(function (error) {
            alert(error.message || (isUpdate ? "Modifica prodotto non riuscita" : "Pubblicazione prodotto non riuscita"));
            publicationPublishButton.disabled = false;
            publicationPublishButton.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i> ' + (isUpdate ? "Aggiorna" : "Pubblica");
        });
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

    if (publicationModalElement) {
        if (publicationModalElement.parentElement !== document.body) {
            document.body.appendChild(publicationModalElement);
        }
        publicationModal = bootstrap.Modal.getOrCreateInstance(publicationModalElement);
        publicationModalElement.addEventListener("show.bs.modal", function () {
            document.body.classList.add("product-publication-modal-open");
        });
        publicationModalElement.addEventListener("hidden.bs.modal", function () {
            document.body.classList.remove("product-publication-modal-open");
            publicationPlatform = "";
            publicationMode = "publish";
            resetPublicationCopyPanel();
        });
        document.querySelectorAll(".product-publish-btn").forEach(function (button) {
            button.addEventListener("click", function () {
                openPublicationModal(button.dataset.platform, "publish");
            });
        });
        document.querySelectorAll(".product-edit-platform-btn").forEach(function (button) {
            button.addEventListener("click", function () {
                openPublicationModal(button.dataset.platform, "update");
            });
        });
        if (publicationSaveButton) {
            publicationSaveButton.addEventListener("click", savePublicationDraft);
        }
        if (publicationPublishButton) {
            publicationPublishButton.addEventListener("click", publishProductDraft);
        }
        if (publicationCopySearchButton) {
            publicationCopySearchButton.addEventListener("click", searchPublicationCopyValues);
        }
        if (publicationCopySearch) {
            publicationCopySearch.addEventListener("keydown", function (event) {
                if (event.key === "Enter") {
                    event.preventDefault();
                    searchPublicationCopyValues();
                }
            });
        }
    }

    if (imageCopyModalElement) {
        if (imageCopyModalElement.parentElement !== document.body) {
            document.body.appendChild(imageCopyModalElement);
        }
        imageCopyModal = bootstrap.Modal.getOrCreateInstance(imageCopyModalElement);
        imageCopyModalElement.addEventListener("show.bs.modal", function () {
            document.body.classList.add("product-image-copy-modal-open");
        });
        imageCopyModalElement.addEventListener("shown.bs.modal", function () {
            resetImageCopyState();
            if (imageCopySearch) {
                imageCopySearch.focus();
            }
        });
        imageCopyModalElement.addEventListener("hidden.bs.modal", function () {
            document.body.classList.remove("product-image-copy-modal-open");
            resetImageCopyState();
            if (imageCopySearch) {
                imageCopySearch.value = "";
            }
            if (imageCopyResults) {
                imageCopyResults.innerHTML = '<div class="text-muted">Cerca un prodotto sorgente.</div>';
            }
        });
        if (imageCopyOpenButton) {
            imageCopyOpenButton.addEventListener("click", function () {
                imageCopyModal.show();
            });
        }
        if (imageCopySearchButton) {
            imageCopySearchButton.addEventListener("click", searchImagesToCopy);
        }
        if (imageCopySearch) {
            imageCopySearch.addEventListener("keydown", function (event) {
                if (event.key === "Enter") {
                    event.preventDefault();
                    searchImagesToCopy();
                }
            });
        }
        if (imageCopyConfirmButton) {
            imageCopyConfirmButton.addEventListener("click", copySelectedImages);
            resetImageCopyState();
        }
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
