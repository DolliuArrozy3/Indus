const entradaTexto = document.querySelector('.tarjeta-texto:not(.panel-traduccion) .campo-texto');
const cajaResultadoOk = document.querySelector('.estado-resultado-ok');
const cajaCargando = document.querySelector('.estado-cargando');
const cajaError = document.querySelector('.estado-error');
const salidaTexto = document.querySelector('.panel-traduccion .campo-texto');
const btnReintentar = document.querySelector('.btn-reintentar');
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

let temporizador;

function mostrarEstado(estado) {
  if (cajaResultadoOk) cajaResultadoOk.classList.add('d-none');
  if (cajaCargando) cajaCargando.classList.add('d-none');
  if (cajaError) cajaError.classList.add('d-none');

  if (estado === 'ok' && cajaResultadoOk) {
    cajaResultadoOk.classList.remove('d-none');
  } else if (estado === 'cargando' && cajaCargando) {
    cajaCargando.classList.remove('d-none');
  } else if (estado === 'error' && cajaError) {
    cajaError.classList.remove('d-none');
  }
}

if (entradaTexto) {
  entradaTexto.addEventListener('input', () => {
    clearTimeout(temporizador);
    const texto = entradaTexto.value.trim();

    if (texto === '') {
      mostrarEstado('ok');
      if (salidaTexto) salidaTexto.value = '';
      return;
    }

    mostrarEstado('cargando');

    temporizador = setTimeout(() => {
      const simulacionError = Math.random() < 0.15;

      if (simulacionError) {
        mostrarEstado('error');
      } else {
        mostrarEstado('ok');
        if (salidaTexto) salidaTexto.value = "[Traducción simulada] " + texto;
      }
    }, 1200);
  });
}

if (btnReintentar) {
  btnReintentar.addEventListener('click', () => {
    mostrarEstado('cargando');
    setTimeout(() => {
      mostrarEstado('ok');
      if (salidaTexto && entradaTexto) salidaTexto.value = "[Traducción corregida] " + entradaTexto.value;
    }, 1000);
  });
}

if (botonIntercambiar) {
  botonIntercambiar.addEventListener('click', () => {
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

    if (entradaTexto) entradaTexto.value = '';
    if (salidaTexto) salidaTexto.value = '';
    mostrarEstado('ok');
  });
}

function activarArchivoCargado() {
  if (estadoVacio && estadoCargando && lateralVacio && lateralListo && btnEnviarTraducir) {
    estadoVacio.classList.add('d-none');
    estadoCargando.classList.remove('d-none');
    lateralVacio.classList.add('d-none');
    lateralListo.classList.remove('d-none');
    btnEnviarTraducir.disabled = false;
    btnEnviarTraducir.classList.add('activo');
  }
}

if (btnBuscar) btnBuscar.addEventListener('click', activarArchivoCargado);
if (btnReemplazar) btnReemplazar.addEventListener('click', activarArchivoCargado);

if (btnQuitar) {
  btnQuitar.addEventListener('click', () => {
    if (estadoCargando && estadoVacio && lateralListo && lateralVacio && btnEnviarTraducir) {
      estadoCargando.classList.add('d-none');
      estadoVacio.classList.remove('d-none');
      lateralListo.classList.add('d-none');
      lateralVacio.classList.remove('d-none');
      btnEnviarTraducir.disabled = true;
      btnEnviarTraducir.classList.remove('activo');
    }
  });
}

if (btnEnviarTraducir) {
  btnEnviarTraducir.addEventListener('click', () => {
    if (lateralListo && lateralProgreso && lblEncabezadoDoc && grupoBotonesCarga && lblEstadoCurso) {
      lateralListo.classList.add('d-none');
      lateralProgreso.classList.remove('d-none');
      lblEncabezadoDoc.innerText = "Tu documento";
      grupoBotonesCarga.classList.add('d-none');
      lblEstadoCurso.classList.remove('d-none');
      btnEnviarTraducir.classList.add('d-none');
    }

    let porcentaje = 0;
    const barra = document.getElementById('barra-llenado');
    const txtPorcentaje = document.getElementById('num-porcentaje');
    
    const intervalo = setInterval(() => {
      porcentaje += 5;
      if (porcentaje <= 100) {
        if (barra) barra.style.width = porcentaje + '%';
        if (txtPorcentaje) txtPorcentaje.innerText = porcentaje + ' %';
      }
      
      if (porcentaje >= 100) {
        clearInterval(intervalo);
        setTimeout(() => {
          if (seccionCargaCompleta) seccionCargaCompleta.classList.add('d-none');
          if (seccionVisorFinal) seccionVisorFinal.classList.remove('d-none');
        }, 600);
      }
    }, 150);
  });
}


