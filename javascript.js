const entradaTexto = document.querySelector('.tarjeta-texto:not(.panel-traduccion) .campo-texto');
let cajaResultadoOk = document.querySelector('.estado-resultado-ok');
let cajaCargando = document.querySelector('.estado-cargando');
let cajaError = document.querySelector('.estado-error');
const salidaTexto = document.querySelector('.panel-traduccion .campo-texto');
let btnReintentar = document.querySelector('.btn-reintentar');
const botonIntercambiar = document.querySelector('.btn-intercambiar');

const btnBuscar = document.getElementById('btn-buscar');
const btnReemplazar = document.getElementById('btn-reemplazar');
const btnQuitar = document.getElementById('btn-quitar');
const btnEnviarTraducir = document.getElementById('btn-enviar-traducir');

const estadoVacio = document.getElementById('doc-estado-vacio');
const estadoCargando = document.getElementById('doc-estado-cargado');
const lateralVacio = document.getElementById('lateral-estado-vacio');
const lateralListo = document.getElementById('lateral-estado-listo');
const lateralProgreso = document.getElementById('lateral-estado-progreso');

const lblEncabezadoDoc = document.getElementById('txt-encabezado-doc');
const lblEstadoCurso = document.getElementById('lbl-estado-curso');
const grupoBotonesCarga = document.getElementById('grupo-botones-carga');
const seccionCargaCompleta = document.getElementById('seccion-carga');
const seccionVisorFinal = document.getElementById('seccion-visor');

// Base de la API: si se sirve desde otro puerto (ej. Live Server 8080), apunta al puerto 5000 de Flask
const API_BASE = (window.location.port && window.location.port !== '5000')
  ? `${window.location.protocol}//${window.location.hostname || '127.0.0.1'}:5000`
  : '';

let temporizador;
let controladorPeticionTexto = null;
let ultimoTextoSolicitado = '';

// Inicializar dinámicamente los contenedores de estado en el panel de traducción
// utilizando las clases ya definidas en estilo-texto.css sin modificar traductor-texto.html
(function inicializarEstadosPanelTexto() {
  const panelTraduccion = document.querySelector('.panel-traduccion');
  if (!panelTraduccion || !salidaTexto) return;

  if (!cajaResultadoOk) {
    cajaResultadoOk = salidaTexto;
  }

  if (!cajaCargando) {
    cajaCargando = document.createElement('div');
    cajaCargando.className = 'estado-cargando d-none';
    cajaCargando.innerHTML = '<div class="spinner"></div><p>Traduciendo texto...</p>';
    panelTraduccion.appendChild(cajaCargando);
  }

  if (!cajaError) {
    cajaError = document.createElement('div');
    cajaError.className = 'estado-error d-none';
    cajaError.innerHTML = `
      <div class="alerta-error">
        <div class="icono-error">⚠️</div>
        <p class="mensaje-error-texto">No se pudo completar la traducción.</p>
        <button type="button" class="btn-reintentar">↻ Reintentar</button>
      </div>
    `;
    panelTraduccion.appendChild(cajaError);
    btnReintentar = cajaError.querySelector('.btn-reintentar');
  }
})();

function mostrarEstado(estado, mensajeError) {
  if (cajaResultadoOk) cajaResultadoOk.classList.add('d-none');
  if (cajaCargando) cajaCargando.classList.add('d-none');
  if (cajaError) cajaError.classList.add('d-none');

  if (estado === 'ok' && cajaResultadoOk) {
    cajaResultadoOk.classList.remove('d-none');
  } else if (estado === 'cargando' && cajaCargando) {
    cajaCargando.classList.remove('d-none');
  } else if (estado === 'error' && cajaError) {
    if (mensajeError) {
      const nodoMsg = cajaError.querySelector('.mensaje-error-texto');
      if (nodoMsg) nodoMsg.innerText = mensajeError;
    }
    cajaError.classList.remove('d-none');
  }
}

function obtenerIdiomasTexto() {
  const selectores = document.querySelectorAll('.barra-idiomas .txt-idioma');
  if (selectores.length >= 2) {
    return {
      origen: selectores.item(0).innerText.trim(),
      destino: selectores.item(1).innerText.trim(),
    };
  }
  return { origen: 'Inglés', destino: 'Español' };
}

async function solicitarTraduccionTexto(forzar = false) {
  if (!entradaTexto) return;
  const texto = entradaTexto.value.trim();

  if (texto === '') {
    if (controladorPeticionTexto) {
      controladorPeticionTexto.abort();
      controladorPeticionTexto = null;
    }
    ultimoTextoSolicitado = '';
    mostrarEstado('ok');
    if (salidaTexto) salidaTexto.value = '';
    return;
  }

  const { origen, destino } = obtenerIdiomasTexto();
  const claveSolicitud = `${origen}|${destino}|${texto}`;
  if (!forzar && claveSolicitud === ultimoTextoSolicitado) {
    return;
  }
  ultimoTextoSolicitado = claveSolicitud;

  if (controladorPeticionTexto) {
    controladorPeticionTexto.abort();
  }
  controladorPeticionTexto = new AbortController();

  mostrarEstado('cargando');

  try {
    const respuesta = await fetch(`${API_BASE}/api/translate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: entradaTexto.value,
        source_lang: origen,
        target_lang: destino,
      }),
      signal: controladorPeticionTexto.signal,
    });

    let datos = null;
    try {
      datos = await respuesta.json();
    } catch (_e) {
      throw new Error('Respuesta inválida del servidor.');
    }

    if (!respuesta.ok || !datos || datos.status !== 'ok') {
      const msgError = (datos && datos.error)
        ? datos.error
        : `Error al traducir el texto (HTTP ${respuesta.status}).`;
      ultimoTextoSolicitado = '';
      mostrarEstado('error', msgError);
      return;
    }

    if (salidaTexto) {
      salidaTexto.value = datos.translated_text || '';
    }
    mostrarEstado('ok');
  } catch (err) {
    if (err && err.name === 'AbortError') {
      return;
    }
    ultimoTextoSolicitado = '';
    mostrarEstado(
      'error',
      err && err.message && err.message !== 'Failed to fetch'
        ? err.message
        : 'Error de conexión con el servidor. Verifica que el backend Flask esté en ejecución.'
    );
  }
}

if (entradaTexto) {
  entradaTexto.addEventListener('input', () => {
    clearTimeout(temporizador);
    const texto = entradaTexto.value.trim();

    if (texto === '') {
      if (controladorPeticionTexto) {
        controladorPeticionTexto.abort();
        controladorPeticionTexto = null;
      }
      ultimoTextoSolicitado = '';
      mostrarEstado('ok');
      if (salidaTexto) salidaTexto.value = '';
      return;
    }

    temporizador = setTimeout(() => {
      solicitarTraduccionTexto(false);
    }, 600);
  });
}

if (btnReintentar) {
  btnReintentar.addEventListener('click', () => {
    solicitarTraduccionTexto(true);
  });
}

function intercambiarIdiomasTexto() {
  const selectores = document.querySelectorAll('.barra-idiomas .txt-idioma');
  const indicadores = document.querySelectorAll('.encabezado-tarjeta .indicador-idioma');

  if (selectores.length >= 2) {
    const selectorIzquierdo = selectores.item(0);
    const selectorDerecho = selectores.item(1);

    const textoTemporalSuperior = selectorIzquierdo.innerText;
    selectorIzquierdo.innerText = selectorDerecho.innerText;
    selectorDerecho.innerText = textoTemporalSuperior;
  }

  if (indicadores.length >= 2) {
    const indicadorIzquierdo = indicadores.item(0);
    const indicadorDerecho = indicadores.item(1);

    const textoTemporalTarjeta = indicadorIzquierdo.innerText;
    indicadorIzquierdo.innerText = indicadorDerecho.innerText;
    indicadorDerecho.innerText = textoTemporalTarjeta;
  }

  ultimoTextoSolicitado = '';
  if (entradaTexto) entradaTexto.value = '';
  if (salidaTexto) salidaTexto.value = '';
  mostrarEstado('ok');
}

if (botonIntercambiar) {
  botonIntercambiar.addEventListener('click', intercambiarIdiomasTexto);
}

// =========================================================================
// FUNCIONALIDAD B: TRADUCTOR DE ARCHIVOS PDF
// =========================================================================

let archivoPdfSeleccionado = null;
let trabajoActual = null;
let intervaloEstadoPdf = null;
let paginaVisorActual = 1;
let totalPaginasVisor = 1;
let zoomVisorActual = 100;

const lblNombreArchivo = document.getElementById('lbl-nombre-archivo');
const lblDetallesArchivo = document.getElementById('lbl-detalles-archivo');
const zonaArrastre = document.querySelector('.zona-arrastre');
const btnIntercambiarAr = document.querySelector('.btn-intercambiar-ar');

// Crear input de archivo oculto para seleccionar PDFs reales sin alterar el HTML
let inputArchivoOculto = null;
if (seccionCargaCompleta) {
  inputArchivoOculto = document.createElement('input');
  inputArchivoOculto.type = 'file';
  inputArchivoOculto.accept = '.pdf,application/pdf';
  inputArchivoOculto.className = 'd-none';
  document.body.appendChild(inputArchivoOculto);

  inputArchivoOculto.addEventListener('change', (evento) => {
    const archivos = evento.target.files;
    if (archivos && archivos.length > 0) {
      manejarSeleccionArchivo(archivos[0]);
    }
    inputArchivoOculto.value = '';
  });
}

function formatearTamanoBytes(bytes) {
  if (typeof bytes !== 'number' || isNaN(bytes)) return '0 KB';
  const mb = bytes / (1024 * 1024);
  if (mb >= 0.1) {
    return mb.toFixed(1).replace('.', ',') + ' MB';
  }
  const kb = Math.max(1, Math.round(bytes / 1024));
  return kb + ' KB';
}

function obtenerIdiomasArchivos() {
  const spans = document.querySelectorAll('.barra-idiomas-archivos .selector-idioma-ar span:first-child');
  if (spans.length >= 2) {
    return {
      origen: spans.item(0).innerText.trim(),
      destino: spans.item(1).innerText.trim(),
    };
  }
  return { origen: 'Inglés', destino: 'Español' };
}

if (btnIntercambiarAr) {
  btnIntercambiarAr.addEventListener('click', () => {
    const spans = document.querySelectorAll('.barra-idiomas-archivos .selector-idioma-ar span:first-child');
    if (spans.length >= 2) {
      const temp = spans.item(0).innerText;
      spans.item(0).innerText = spans.item(1).innerText;
      spans.item(1).innerText = temp;
    }
  });
}

function activarArchivoCargado() {
  if (estadoVacio && estadoCargando && lateralVacio && lateralListo && btnEnviarTraducir) {
    estadoVacio.classList.add('d-none');
    estadoCargando.classList.remove('d-none');
    lateralVacio.classList.add('d-none');
    lateralListo.classList.remove('d-none');
    if (lateralProgreso) lateralProgreso.classList.add('d-none');
    btnEnviarTraducir.classList.remove('d-none');
    btnEnviarTraducir.disabled = false;
    btnEnviarTraducir.classList.add('activo');
  }
}

function mostrarErrorValidacionArchivo(nombreArchivo, detalleTamano, mensajeError) {
  if (estadoVacio && estadoCargando && lateralVacio && lateralListo && btnEnviarTraducir) {
    estadoVacio.classList.add('d-none');
    estadoCargando.classList.remove('d-none');
    lateralVacio.classList.add('d-none');
    lateralListo.classList.remove('d-none');
    if (lateralProgreso) lateralProgreso.classList.add('d-none');

    if (lblNombreArchivo) lblNombreArchivo.innerText = nombreArchivo || 'Archivo inválido';
    if (lblDetallesArchivo) lblDetallesArchivo.innerText = detalleTamano || 'No disponible';
    if (grupoBotonesCarga) grupoBotonesCarga.classList.remove('d-none');
    if (lblEstadoCurso) lblEstadoCurso.classList.add('d-none');

    const spanListo = lateralListo.querySelector('span');
    if (spanListo) {
      spanListo.innerText = `⚠️ ${mensajeError}`;
      spanListo.style.color = '#E53E3E';
    }

    btnEnviarTraducir.classList.remove('d-none');
    btnEnviarTraducir.disabled = true;
    btnEnviarTraducir.classList.remove('activo');
  }
}

async function manejarSeleccionArchivo(archivo) {
  if (!archivo) return;

  archivoPdfSeleccionado = null;
  const nombre = archivo.name || 'documento.pdf';
  const tamanoTexto = formatearTamanoBytes(archivo.size);

  if (lblNombreArchivo) lblNombreArchivo.innerText = nombre;
  if (lblDetallesArchivo) lblDetallesArchivo.innerText = `${tamanoTexto} • Validando documento...`;
  if (lblEncabezadoDoc) lblEncabezadoDoc.innerText = 'Documento original';
  if (grupoBotonesCarga) grupoBotonesCarga.classList.remove('d-none');
  if (lblEstadoCurso) lblEstadoCurso.classList.add('d-none');

  // Validación preliminar en el frontend (extensión y tamaño máximo 10 MB)
  if (!nombre.toLowerCase().endsWith('.pdf')) {
    mostrarErrorValidacionArchivo(
      nombre,
      tamanoTexto,
      'Formato no permitido. Solo se aceptan archivos en formato PDF (.pdf).'
    );
    return;
  }

  if (archivo.size === 0) {
    mostrarErrorValidacionArchivo(nombre, '0 KB', 'El archivo seleccionado está vacío.');
    return;
  }

  const maxBytes = 10 * 1024 * 1024;
  if (archivo.size > maxBytes) {
    mostrarErrorValidacionArchivo(
      nombre,
      tamanoTexto,
      `El archivo supera el límite máximo permitido de 10 MB (${tamanoTexto}).`
    );
    return;
  }

  // Mostrar estado de validación mientras el backend verifica páginas e integridad
  activarArchivoCargado();
  btnEnviarTraducir.disabled = true;
  btnEnviarTraducir.classList.remove('activo');
  const spanListo = lateralListo ? lateralListo.querySelector('span') : null;
  if (spanListo) {
    spanListo.innerText = '⏳ Validando documento PDF...';
    spanListo.style.color = '#718096';
  }

  try {
    const formData = new FormData();
    formData.append('file', archivo);

    const respuesta = await fetch(`${API_BASE}/api/translate/pdf/validate`, {
      method: 'POST',
      body: formData,
    });

    const datos = await respuesta.json();
    if (!respuesta.ok || datos.status !== 'ok') {
      mostrarErrorValidacionArchivo(
        nombre,
        tamanoTexto,
        datos.error || 'El documento PDF no es válido o no puede procesarse.'
      );
      return;
    }

    archivoPdfSeleccionado = archivo;
    const paginas = datos.page_count;
    const textoPaginas = paginas === 1 ? '1 página' : `${paginas} páginas`;
    if (lblDetallesArchivo) {
      lblDetallesArchivo.innerText = `${formatearTamanoBytes(datos.file_size_bytes)} • ${textoPaginas}`;
    }
    if (spanListo) {
      spanListo.innerText = '✓ Tu archivo está listo para traducir.';
      spanListo.style.color = '';
    }
    btnEnviarTraducir.disabled = false;
    btnEnviarTraducir.classList.add('activo');
  } catch (_err) {
    mostrarErrorValidacionArchivo(
      nombre,
      tamanoTexto,
      'No se pudo conectar con el servidor para validar el PDF. Verifica que el backend esté activo.'
    );
  }
}

function abrirSelectorArchivo() {
  if (inputArchivoOculto) {
    inputArchivoOculto.click();
  }
}

if (btnBuscar) btnBuscar.addEventListener('click', abrirSelectorArchivo);
if (btnReemplazar) btnReemplazar.addEventListener('click', abrirSelectorArchivo);

// Soporte para arrastrar y soltar (Drag & Drop) en la zona de carga
if (zonaArrastre) {
  ['dragenter', 'dragover'].forEach((evtName) => {
    zonaArrastre.addEventListener(evtName, (e) => {
      e.preventDefault();
      e.stopPropagation();
    });
  });

  zonaArrastre.addEventListener('drop', (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      if (e.dataTransfer.files.length > 1) {
        mostrarErrorValidacionArchivo(
          e.dataTransfer.files[0].name,
          '',
          'Solo se permite cargar un documento PDF por operación.'
        );
        return;
      }
      manejarSeleccionArchivo(e.dataTransfer.files[0]);
    }
  });
}

if (btnQuitar) {
  btnQuitar.addEventListener('click', () => {
    if (intervaloEstadoPdf) {
      clearInterval(intervaloEstadoPdf);
      intervaloEstadoPdf = null;
    }
    archivoPdfSeleccionado = null;
    trabajoActual = null;
    if (estadoCargando && estadoVacio && lateralListo && lateralVacio && btnEnviarTraducir) {
      estadoCargando.classList.add('d-none');
      estadoVacio.classList.remove('d-none');
      lateralListo.classList.add('d-none');
      if (lateralProgreso) lateralProgreso.classList.add('d-none');
      lateralVacio.classList.remove('d-none');
      if (lblEncabezadoDoc) lblEncabezadoDoc.innerText = 'Documento original';
      btnEnviarTraducir.classList.remove('d-none');
      btnEnviarTraducir.disabled = true;
      btnEnviarTraducir.classList.remove('activo');
    }
  });
}

function actualizarPasosUI(estadoJob, pasoActual, usadoOcr) {
  const itemsPaso = document.querySelectorAll('.lista-pasos-traduccion .paso-item');
  if (itemsPaso.length < 3) return;

  const pasoExtraccion = itemsPaso.item(0);
  const pasoTraduccion = itemsPaso.item(1);
  const pasoGeneracion = itemsPaso.item(2);

  const etiquetaExtraccion = usadoOcr || estadoJob === 'ocr' ? 'Extracción / OCR' : 'Extracción';

  if (pasoActual === 'extraction' || estadoJob === 'validating' || estadoJob === 'extracting' || estadoJob === 'ocr') {
    pasoExtraccion.className = 'paso-item paso-activo';
    pasoExtraccion.innerHTML = `⏳ ${etiquetaExtraccion} <span>${estadoJob === 'ocr' ? 'Aplicando OCR' : 'En curso'}</span>`;

    pasoTraduccion.className = 'paso-item paso-pendiente';
    pasoTraduccion.innerHTML = '○ Traducción <span>Pendiente</span>';

    pasoGeneracion.className = 'paso-item paso-pendiente';
    pasoGeneracion.innerHTML = '○ Generación <span>Pendiente</span>';
  } else if (pasoActual === 'translation' || estadoJob === 'translating') {
    pasoExtraccion.className = 'paso-item paso-completado';
    pasoExtraccion.innerHTML = `✓ ${etiquetaExtraccion} <span>Completada</span>`;

    pasoTraduccion.className = 'paso-item paso-activo';
    pasoTraduccion.innerHTML = '⏳ Traducción <span>En curso</span>';

    pasoGeneracion.className = 'paso-item paso-pendiente';
    pasoGeneracion.innerHTML = '○ Generación <span>Pendiente</span>';
  } else if (pasoActual === 'generation' || estadoJob === 'generating') {
    pasoExtraccion.className = 'paso-item paso-completado';
    pasoExtraccion.innerHTML = `✓ ${etiquetaExtraccion} <span>Completada</span>`;

    pasoTraduccion.className = 'paso-item paso-completado';
    pasoTraduccion.innerHTML = '✓ Traducción <span>Completada</span>';

    pasoGeneracion.className = 'paso-item paso-activo';
    pasoGeneracion.innerHTML = '⏳ Generación <span>En curso</span>';
  } else if (estadoJob === 'completed') {
    pasoExtraccion.className = 'paso-item paso-completado';
    pasoExtraccion.innerHTML = `✓ ${etiquetaExtraccion} <span>Completada</span>`;

    pasoTraduccion.className = 'paso-item paso-completado';
    pasoTraduccion.innerHTML = '✓ Traducción <span>Completada</span>';

    pasoGeneracion.className = 'paso-item paso-completado';
    pasoGeneracion.innerHTML = '✓ Generación <span>Completada</span>';
  }
}

function mostrarErrorProcesamientoPdf(mensaje) {
  if (intervaloEstadoPdf) {
    clearInterval(intervaloEstadoPdf);
    intervaloEstadoPdf = null;
  }

  if (grupoBotonesCarga) grupoBotonesCarga.classList.remove('d-none');
  if (lblEstadoCurso) {
    lblEstadoCurso.classList.remove('d-none');
    lblEstadoCurso.innerText = `🔴 Error en el procesamiento`;
  }

  if (lateralProgreso) lateralProgreso.classList.add('d-none');
  if (lateralListo) {
    lateralListo.classList.remove('d-none');
    const spanListo = lateralListo.querySelector('span');
    if (spanListo) {
      spanListo.innerText = `⚠️ ${mensaje}`;
      spanListo.style.color = '#E53E3E';
    }
  }

  if (btnEnviarTraducir) {
    btnEnviarTraducir.classList.remove('d-none');
    btnEnviarTraducir.disabled = false;
    btnEnviarTraducir.classList.add('activo');
  }
}

function renderizarPaginaEnVisor() {
  if (!trabajoActual || !seccionVisorFinal) return;

  const spanPagina = seccionVisorFinal.querySelector('.controles-paginas-visor span');
  if (spanPagina) {
    spanPagina.innerText = `Página ${paginaVisorActual} de ${totalPaginasVisor}`;
  }

  const spanZoom = seccionVisorFinal.querySelector('.txt-zoom-porcentaje');
  if (spanZoom) {
    spanZoom.innerText = `${zoomVisorActual}%`;
  }

  const hojaBlanca = seccionVisorFinal.querySelector('.hoja-blanca-pdf');
  if (!hojaBlanca) return;

  const anchoBase = Math.round(700 * (zoomVisorActual / 100));
  hojaBlanca.style.maxWidth = `${anchoBase}px`;
  hojaBlanca.style.padding = '16px';

  const urlImagenPagina = `${API_BASE}/api/translate/pdf/${trabajoActual.job_id}/page/${paginaVisorActual}`;
  const previewTextoObj = (trabajoActual.pages_preview || []).find(
    (p) => p.page_number === paginaVisorActual
  );
  const textoRespaldo = previewTextoObj ? previewTextoObj.translated_text : '';

  hojaBlanca.innerHTML = '';
  const imgPagina = document.createElement('img');
  imgPagina.src = urlImagenPagina;
  imgPagina.alt = `Página ${paginaVisorActual} del documento traducido`;
  imgPagina.style.width = '100%';
  imgPagina.style.height = 'auto';
  imgPagina.style.display = 'block';

  imgPagina.onerror = () => {
    hojaBlanca.style.padding = '50px';
    hojaBlanca.innerHTML = `
      <div class="encabezado-hoja-simulada">
        <strong>INDUS</strong>
        <span>PÁGINA ${paginaVisorActual}</span>
      </div>
      <hr class="linea-separadora-pdf">
      <div style="white-space: pre-wrap; font-family: sans-serif; font-size: 14px; line-height: 1.6;"></div>
    `;
    const contenedorTexto = hojaBlanca.querySelector('div:last-child');
    if (contenedorTexto) contenedorTexto.innerText = textoRespaldo;
  };

  hojaBlanca.appendChild(imgPagina);
}

function mostrarVisorFinalConResultado(datosJob) {
  trabajoActual = datosJob;
  paginaVisorActual = 1;
  totalPaginasVisor = Math.max(1, datosJob.output_pages_count || 1);
  zoomVisorActual = 100;

  if (seccionCargaCompleta) seccionCargaCompleta.classList.add('d-none');
  if (seccionVisorFinal) {
    seccionVisorFinal.classList.remove('d-none');

    const tituloArchivoFinal = seccionVisorFinal.querySelector('.nombre-archivo-final');
    if (tituloArchivoFinal) {
      tituloArchivoFinal.innerText = datosJob.output_filename || 'documento-es.pdf';
    }

    const detallesArchivoFinal = seccionVisorFinal.querySelector('.detalles-archivo-final');
    if (detallesArchivoFinal) {
      const txtPags = totalPaginasVisor === 1 ? '1 página' : `${totalPaginasVisor} páginas`;
      detallesArchivoFinal.innerText = `${txtPags} • ${datosJob.source_lang_name || 'Inglés'} ➜ ${datosJob.target_lang_name || 'Español'} • ✓ Traducción completada`;
    }

    renderizarPaginaEnVisor();
  }
}

// Controles del visor existente (paginación, zoom y descarga)
if (seccionVisorFinal) {
  const btnDescargarFinal = seccionVisorFinal.querySelector('.btn-descargar-pdf-final');
  if (btnDescargarFinal) {
    btnDescargarFinal.addEventListener('click', () => {
      if (!trabajoActual || !trabajoActual.download_url) return;
      const enlace = document.createElement('a');
      enlace.href = `${API_BASE}${trabajoActual.download_url}`;
      enlace.download = trabajoActual.output_filename || 'documento-traducido.pdf';
      document.body.appendChild(enlace);
      enlace.click();
      document.body.removeChild(enlace);
    });
  }

  const botonesFlecha = seccionVisorFinal.querySelectorAll('.controles-paginas-visor .btn-flecha-visor');
  if (botonesFlecha.length >= 2) {
    const btnAnterior = botonesFlecha.item(0);
    const btnSiguiente = botonesFlecha.item(1);

    btnAnterior.addEventListener('click', () => {
      if (paginaVisorActual > 1) {
        paginaVisorActual -= 1;
        renderizarPaginaEnVisor();
      }
    });

    btnSiguiente.addEventListener('click', () => {
      if (paginaVisorActual < totalPaginasVisor) {
        paginaVisorActual += 1;
        renderizarPaginaEnVisor();
      }
    });
  }

  const botonesZoom = seccionVisorFinal.querySelectorAll('.controles-zoom-visor .btn-zoom-operacion');
  if (botonesZoom.length >= 2) {
    const btnZoomMenos = botonesZoom.item(0);
    const btnZoomMas = botonesZoom.item(1);

    btnZoomMenos.addEventListener('click', () => {
      if (zoomVisorActual > 50) {
        zoomVisorActual -= 25;
        renderizarPaginaEnVisor();
      }
    });

    btnZoomMas.addEventListener('click', () => {
      if (zoomVisorActual < 200) {
        zoomVisorActual += 25;
        renderizarPaginaEnVisor();
      }
    });
  }
}

if (btnEnviarTraducir) {
  btnEnviarTraducir.addEventListener('click', async () => {
    if (!archivoPdfSeleccionado) {
      abrirSelectorArchivo();
      return;
    }

    const { origen, destino } = obtenerIdiomasArchivos();

    if (lateralListo && lateralProgreso && lblEncabezadoDoc && grupoBotonesCarga && lblEstadoCurso) {
      lateralListo.classList.add('d-none');
      lateralProgreso.classList.remove('d-none');
      lblEncabezadoDoc.innerText = 'Tu documento';
      grupoBotonesCarga.classList.add('d-none');
      lblEstadoCurso.innerText = '🟢 Traducción en curso';
      lblEstadoCurso.classList.remove('d-none');
      btnEnviarTraducir.classList.add('d-none');
    }

    const notaInformativa = document.querySelector('.nota-informativa-ar');
    if (notaInformativa) {
      notaInformativa.innerText = `El documento se está traduciendo al ${destino.toLowerCase()}.`;
    }

    const txtBarra = document.querySelector('.txt-barra-progreso');
    const barra = document.getElementById('barra-llenado');
    const txtPorcentaje = document.getElementById('num-porcentaje');

    if (txtBarra) txtBarra.innerText = 'Archivo recibido. Iniciando procesamiento...';
    if (barra) barra.style.width = '0%';
    if (txtPorcentaje) txtPorcentaje.innerText = '—';
    actualizarPasosUI('validating', 'extraction', false);

    try {
      const formData = new FormData();
      formData.append('file', archivoPdfSeleccionado);
      formData.append('source_lang', origen);
      formData.append('target_lang', destino);
      formData.append('async', 'true');

      const respuesta = await fetch(`${API_BASE}/api/translate/pdf?async=true`, {
        method: 'POST',
        body: formData,
      });

      const datosIniciales = await respuesta.json();
      if (!respuesta.ok || datosIniciales.status === 'error') {
        mostrarErrorProcesamientoPdf(
          datosIniciales.error || 'No se pudo iniciar la traducción del documento PDF.'
        );
        return;
      }

      const jobId = datosIniciales.job_id;
      if (!jobId) {
        mostrarErrorProcesamientoPdf('No se recibió un identificador de procesamiento válido.');
        return;
      }

      // Consultar periódicamente el estado real del procesamiento en el backend
      intervaloEstadoPdf = setInterval(async () => {
        try {
          const respEstado = await fetch(`${API_BASE}/api/translate/pdf/${jobId}`);
          const estadoJob = await respEstado.json();

          if (txtBarra && estadoJob.status_message) {
            txtBarra.innerText = estadoJob.status_message;
          }

          if (typeof estadoJob.progress === 'number') {
            if (barra) barra.style.width = `${estadoJob.progress}%`;
            if (txtPorcentaje) txtPorcentaje.innerText = `${estadoJob.progress} %`;
          } else {
            if (barra) barra.style.width = '0%';
            if (txtPorcentaje) txtPorcentaje.innerText = '—';
          }

          actualizarPasosUI(estadoJob.status, estadoJob.step, estadoJob.used_ocr);

          if (estadoJob.status === 'error') {
            clearInterval(intervaloEstadoPdf);
            intervaloEstadoPdf = null;
            mostrarErrorProcesamientoPdf(
              estadoJob.error || 'Ocurrió un error durante la traducción del PDF.'
            );
            return;
          }

          if (estadoJob.status === 'completed') {
            clearInterval(intervaloEstadoPdf);
            intervaloEstadoPdf = null;
            if (barra) barra.style.width = '100%';
            if (txtPorcentaje) txtPorcentaje.innerText = '100 %';
            mostrarVisorFinalConResultado(estadoJob);
          }
        } catch (_pollErr) {
          clearInterval(intervaloEstadoPdf);
          intervaloEstadoPdf = null;
          mostrarErrorProcesamientoPdf('Se perdió la conexión con el servidor durante el procesamiento.');
        }
      }, 450);
    } catch (_err) {
      mostrarErrorProcesamientoPdf(
        'Error de conexión al enviar el archivo al servidor Flask.'
      );
    }
  });
}
