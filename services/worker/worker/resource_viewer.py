"""Standalone WebGL surface smoke using real DAT fields; product viewer remains T010/T020."""

import json
from pathlib import Path
from typing import Any


def write_viewer(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(HTML.replace("__DATA__", json.dumps(payload)))


HTML = """<!doctype html><html lang="en"><meta charset="utf-8">
<title>T006 measured native display diagnostic</title>
<style>body{font:16px sans-serif;max-width:1000px;margin:auto}canvas{width:800px;height:600px}
pre{white-space:pre-wrap}label{display:block}</style>
<h1>Real C3D10 resource diagnostic</h1>
<p>Development only; engineering review pending. Exterior surface only; no volume rendering.
Stress uses each exterior element's raw DAT IP1 xx value, piecewise constant, without averaging.</p>
<label>Displayed field <select id="field"><option value="3">Displacement ux (m)</option>
<option value="4">Raw element IP1 stress xx (Pa)</option></select></label>
<label>View rotation <input id="angle" type="range" min="0" max="6.28" step="0.01" value="0.65">
</label>
<canvas id="view" width="800" height="600"></canvas><pre id="metrics"></pre>
<script id="data" type="application/json">__DATA__</script><script>
const data=JSON.parse(document.getElementById('data').textContent);
const canvas=document.getElementById('view');
const gl=canvas.getContext('webgl',{preserveDrawingBuffer:true});
if(!gl)throw Error('WebGL unavailable');
const extension=gl.getExtension('WEBGL_debug_renderer_info');
const gpu=extension?gl.getParameter(extension.UNMASKED_RENDERER_WEBGL):'unavailable';
const vendor=extension?gl.getParameter(extension.UNMASKED_VENDOR_WEBGL):'unavailable';
function shader(type,source){const s=gl.createShader(type);gl.shaderSource(s,source);
gl.compileShader(s);
if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;}
const program=gl.createProgram();
gl.attachShader(program,shader(gl.VERTEX_SHADER,`attribute vec3 p;attribute float value;
uniform float angle;uniform vec2 range;varying float color;
void main(){vec3 q=p-vec3(.5);float c=cos(angle),s=sin(angle);
vec3 r=vec3(c*q.x+s*q.z,q.y,-s*q.x+c*q.z);
gl_Position=vec4(r.x*1.1,(r.y*.8+r.z*.4)*1.3,r.z*.7-r.y*.2,1.0);
color=clamp((value-range.x)/max(range.y-range.x,1e-12),0.0,1.0);}`));
gl.attachShader(program,shader(gl.FRAGMENT_SHADER,`precision mediump float;varying float color;
void main(){gl_FragColor=vec4(color,.25,1.0-color,1.0);}`));gl.linkProgram(program);
if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));
gl.useProgram(program);const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
const started=performance.now();
gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data.vertices),gl.STATIC_DRAW);
const uploadMs=performance.now()-started;
const p=gl.getAttribLocation(program,'p'),v=gl.getAttribLocation(program,'value');
gl.enableVertexAttribArray(p);gl.enableVertexAttribArray(v);gl.vertexAttribPointer(p,3,gl.FLOAT,false,20,0);
gl.enable(gl.DEPTH_TEST);const times=[];
const result={renderer:gpu,vendor,volume_elements:data.volume_elements,
surface_triangles:data.surface_triangles,buffer_bytes:data.vertices.length*4,upload_ms:uploadMs,
mesh_sha256:data.mesh_sha256,dat_sha256:data.dat_sha256,field:'ux',frame_ms:times};
function draw(){const index=Number(document.getElementById('field').value);
const drawStarted=performance.now();
let lo=Infinity,hi=-Infinity;
for(let i=index;i<data.vertices.length;i+=5){lo=Math.min(lo,data.vertices[i]);
hi=Math.max(hi,data.vertices[i]);}
gl.vertexAttribPointer(v,1,gl.FLOAT,false,20,index*4);
gl.uniform2f(gl.getUniformLocation(program,'range'),lo,hi);
gl.uniform1f(gl.getUniformLocation(program,'angle'),Number(document.getElementById('angle').value));
const before=performance.now();gl.clearColor(.95,.95,.95,1);
gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
gl.drawArrays(gl.TRIANGLES,0,data.vertices.length/5);gl.finish();times.push(performance.now()-before);
if(gl.getError()!==gl.NO_ERROR)throw Error('WebGL draw failed');
result.field=index===3?'ux':'raw element IP1 xx';result.range=[lo,hi];
result.draw_total_ms=performance.now()-drawStarted;
window.openfeaResource=result;
const summary={...result,frame_ms:undefined,frames:times.length};
document.getElementById('metrics').textContent=JSON.stringify(summary,null,2);}
document.getElementById('field').onchange=draw;document.getElementById('angle').oninput=draw;draw();
</script></html>"""
