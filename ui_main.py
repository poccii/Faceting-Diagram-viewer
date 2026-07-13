import re
from pathlib import Path
import numpy as np

from PySide6.QtCore import Qt, QByteArray, QRectF
from PySide6.QtGui import (
    QPainter, QFont, QColor, QPdfWriter, QPageSize, QPageLayout
)
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QMainWindow, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QGridLayout, 
    QDoubleSpinBox, QCheckBox, QGraphicsView, QGraphicsScene, QMessageBox
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QGraphicsSvgItem

import pyqtgraph.opengl as gl

from asc_parser import load_asc
from diagram_generator import DiagramGenerator


class View3DWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3D Facet Viewer")
        self.resize(800, 800)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.view_3d = gl.GLViewWidget()
        self.view_3d.setBackgroundColor('w')
        self.layout.addWidget(self.view_3d)
        
        self.mesh_item = gl.GLMeshItem(smooth=False, drawEdges=False, glOptions='opaque')
        self.view_3d.addItem(self.mesh_item)
        
        self.view_3d.setCameraPosition(distance=5.0, elevation=30)
        
        self.edge_items = []
        self.text_items = []

    def update_3d_view(self, polygons, show_jamb=False):
        for item in self.edge_items:
            self.view_3d.removeItem(item)
        self.edge_items.clear()
        
        for item in self.text_items:
            self.view_3d.removeItem(item)
        self.text_items.clear()

        if not polygons:
            self.mesh_item.setMeshData(vertexes=np.empty((0,3)), faces=np.empty((0,3), dtype=int))
            return

        verts = []
        faces = []
        face_colors = []
        idx = 0
        
        for poly in polygons:
            pts = poly['points']
            section = poly['facet'].section
            
            if section == 'Crown': color = [0.85, 0.95, 1.0, 1.0]
            elif section == 'Pavilion': color = [1.0, 0.97, 0.88, 1.0]
            elif section == 'Table': color = [0.75, 0.9, 1.0, 1.0]
            else: color = [0.8, 0.8, 0.8, 1.0]
            
            v0 = pts[0]
            for i in range(1, len(pts) - 1):
                verts.append(v0)
                verts.append(pts[i])
                verts.append(pts[i+1])
                faces.append([idx, idx+1, idx+2])
                face_colors.append(color)
                idx += 3
                
            perimeter = np.vstack([pts, pts[0]])
            edge_item = gl.GLLinePlotItem(pos=perimeter, color=(0,0,0,1), width=1.5, antialias=True)
            self.view_3d.addItem(edge_item)
            self.edge_items.append(edge_item)
            
            p0, p1 = pts[0], pts[1]
            p2 = pts[2] if len(pts) > 2 else pts[1]
            
            v1, v2 = p1 - p0, p2 - p0
            normal = np.cross(v1, v2)
            norm_len = np.linalg.norm(normal)
            if norm_len > 1e-6:
                normal = normal / norm_len
            else:
                normal = np.array([0, 0, 1])
                
            center = poly['center']
            if np.dot(center, normal) < 0:
                normal = -normal
                
            text_pos = center + normal * 0.05
            
            facet = poly['facet']
            label_str = facet.name
            if show_jamb:
                if facet.section == "Table" or facet.name == "T":
                    label_str = "T"
                else:
                    spec_idx = poly.get('specific_index')
                    if spec_idx is not None:
                        idx_rounded = int(round(spec_idx))
                        jamb_map = {0: "0", 1: "+1", 2: "+2", 3: "+3", 4: "+4", 5: "-3", 6: "-2", 7: "-1"}
                        label_str = jamb_map[idx_rounded % 8]
            
            font = QFont("sans-serif", 10)
            font.setBold(True)
            text_item = gl.GLTextItem(pos=text_pos, text=label_str, font=font, color=QColor(150, 0, 0, 255))
            self.view_3d.addItem(text_item)
            self.text_items.append(text_item)
                
        if verts:
            verts_arr = np.array(verts)
            self.mesh_item.setMeshData(
                vertexes=verts_arr,
                faces=np.array(faces, dtype=int),
                faceColors=np.array(face_colors)
            )
            
            max_dist = np.max(np.linalg.norm(verts_arr, axis=1))
            if max_dist > 0:
                self.view_3d.setCameraPosition(distance=max_dist * 2.5, elevation=30)


class InteractiveSvgView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.svg_item = QGraphicsSvgItem()
        self.scene.addItem(self.svg_item)
        
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setRenderHint(QPainter.Antialiasing)
        self.setAlignment(Qt.AlignCenter)
        self.renderer = None

    def load(self, byte_array):
        self.renderer = QSvgRenderer(byte_array)
        self.svg_item.setSharedRenderer(self.renderer)
        self.scene.setSceneRect(self.svg_item.boundingRect())


class SvgRenderer:
    def __init__(self):
        pass

    def generate_svg(self, diagram, polygons, real_dims=None, show_jamb=False, zoom=1.0, selected_facet_name=None, selected_facet_section=None) -> str:
        if not polygons:
            return self.generate_dummy_svg(zoom)

        all_pts = np.vstack([p['points'] for p in polygons])
        max_val = np.max(np.abs(all_pts))
        if max_val == 0: max_val = 1.0
        
        scale = (120.0 / max_val) * zoom
        
        w_svg = int(680 * zoom)
        h_svg = int(720 * zoom)
        
        svg_header = f"""
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w_svg} {h_svg}" width="{w_svg}" height="{h_svg}">
            <defs>
                <marker id="arrow-start" markerWidth="6" markerHeight="6" refX="0" refY="3" orient="auto">
                    <path d="M6,0 L0,3 L6,6 Z" fill="#555" />
                </marker>
                <marker id="arrow-end" markerWidth="6" markerHeight="6" refX="6" refY="3" orient="auto">
                    <path d="M0,0 L6,3 L0,6 Z" fill="#555" />
                </marker>
            </defs>
            <style>
                .label {{ font: bold 9.5px sans-serif; text-anchor: middle; dominant-baseline: middle; fill: #b71c1c; stroke: rgba(255,255,255,0.9); stroke-width: 3px; paint-order: stroke fill; }}
                .facet-crown {{ fill: #f1f8ff; stroke: #222222; stroke-width: 1.0; stroke-linejoin: round; fill-opacity: 0.9; }}
                .facet-pavilion {{ fill: #fffdf4; stroke: #222222; stroke-width: 1.0; stroke-linejoin: round; fill-opacity: 0.9; }}
                .facet-girdle {{ fill: #f5f5f5; stroke: #666666; stroke-width: 1.0; }}
                .facet-table {{ fill: #e3f2fd; stroke: #222222; stroke-width: 1.5; }}
                .facet-highlight {{ fill: #ffeb3b; stroke: #e65100; stroke-width: 2.0; stroke-linejoin: round; fill-opacity: 0.95; }}
                .dim-line {{ stroke: #555; stroke-width: 1.0; marker-start: url(#arrow-start); marker-end: url(#arrow-end); }}
                .dim-text {{ font: bold 12px sans-serif; fill: #1565c0; text-anchor: middle; dominant-baseline: middle; }}
                .dim-ext {{ stroke: #999; stroke-width: 0.8; stroke-dasharray: 3,3; }}
            </style>
        """
        
        cx_crown, cy_crown = 180 * zoom, 200 * zoom
        cx_end, cy_end     = 500 * zoom, 200 * zoom
        cx_side, cy_side   = 180 * zoom, 520 * zoom
        cx_pav, cy_pav     = 500 * zoom, 520 * zoom
        
        crown_svg = f'<g transform="translate({cx_crown}, {cy_crown})">\n'
        side_svg = f'<g transform="translate({cx_side}, {cy_side})">\n'
        pav_svg = f'<g transform="translate({cx_pav}, {cy_pav})">\n'
        end_svg = f'<g transform="translate({cx_end}, {cy_end})">\n  <g transform="rotate(-90)">\n'

        crown_polys = ""
        crown_texts = ""
        pav_polys = ""
        pav_texts = ""

        xs = all_pts[:, 0] * scale
        ys = all_pts[:, 1] * scale
        zs = all_pts[:, 2] * scale
        
        min_x, max_x = np.min(xs), np.max(xs)
        min_y, max_y = np.min(ys), np.max(ys)
        min_z, max_z = np.min(zs), np.max(zs)

        def get_label(poly):
            facet = poly['facet']
            if show_jamb:
                if facet.section == "Table" or facet.name == "T":
                    return "T"
                spec_idx = poly.get('specific_index')
                if spec_idx is not None:
                    idx_rounded = int(round(spec_idx))
                    jamb_map = {0: "0", 1: "+1", 2: "+2", 3: "+3", 4: "+4", 5: "-3", 6: "-2", 7: "-1"}
                    return jamb_map[idx_rounded % 8]
            return facet.name

        for poly in polygons:
            facet = poly['facet']
            pts = poly['points']
            
            pts_2d_crown = []
            pts_2d_pav = []
            pts_2d_side = []
            pts_2d_end = []
            
            for pt in pts:
                cx, cy, cz = pt[0] * scale, pt[1] * scale, pt[2] * scale
                pts_2d_crown.append(f"{cx},{-cy}")
                pts_2d_pav.append(f"{-cx},{-cy}")
                pts_2d_side.append(f"{cx},{-cz}")
                pts_2d_end.append(f"{cy},{-cz}")
            
            poly_str_crown = " ".join(pts_2d_crown)
            poly_str_pav = " ".join(pts_2d_pav)
            poly_str_side = " ".join(pts_2d_side)
            poly_str_end = " ".join(pts_2d_end)
            
            center_3d = poly['center'] * scale
            lbl_x_cr, lbl_y_cr = center_3d[0], -center_3d[1]
            lbl_x_pv, lbl_y_pv = -center_3d[0], -center_3d[1]

            if selected_facet_name and facet.name == selected_facet_name and facet.section == selected_facet_section:
                cls = "facet-highlight"
            else:
                if facet.section == "Table": cls = "facet-table"
                elif facet.section == "Girdle": cls = "facet-girdle"
                elif facet.section == "Crown": cls = "facet-crown"
                else: cls = "facet-pavilion"
            
            if facet.section in ["Crown", "Table", "Girdle"]:
                crown_polys += f'  <polygon points="{poly_str_crown}" class="{cls}" />\n'
                if facet.section != "Girdle":
                    crown_texts += f'  <text x="{lbl_x_cr}" y="{lbl_y_cr}" class="label">{get_label(poly)}</text>\n'

            if facet.section in ["Pavilion", "Girdle"]:
                pav_polys += f'  <polygon points="{poly_str_pav}" class="{cls}" />\n'
                if facet.section != "Girdle":
                    pav_texts += f'  <text x="{lbl_x_pv}" y="{lbl_y_pv}" class="label">{get_label(poly)}</text>\n'

            side_svg += f'  <polygon points="{poly_str_side}" class="{cls}" />\n'
            end_svg += f'  <polygon points="{poly_str_end}" class="{cls}" />\n'

        crown_svg += crown_polys + crown_texts
        pav_svg += pav_polys + pav_texts

        table_pts = [p['points'] for p in polygons if p['facet'].section == 'Table']
        if table_pts:
            t_pts = np.vstack(table_pts) * scale
            min_tx, max_tx = np.min(t_pts[:, 0]), np.max(t_pts[:, 0])
            min_ty, max_ty = np.min(t_pts[:, 1]), np.max(t_pts[:, 1])
        else:
            min_tx = max_tx = min_ty = max_ty = 0.0

        crown_pts = [p['points'] for p in polygons if p['facet'].section in ['Crown', 'Table']]
        girdle_z_top = np.min(np.vstack(crown_pts)[:, 2]) * scale if crown_pts else 0.0
        
        pav_pts = [p['points'] for p in polygons if p['facet'].section == 'Pavilion']
        girdle_z_bottom = np.max(np.vstack(pav_pts)[:, 2]) * scale if pav_pts else 0.0

        def make_dim(x1, y1, x2, y2, label_key, label_dx=0, label_dy=0):
            if real_dims and label_key in real_dims:
                label_str = f"{label_key} {real_dims[label_key]:.1f}"
            else:
                label_str = label_key
            line = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="dim-line" />\n'
            text = f'<text x="{(x1+x2)/2 + label_dx}" y="{(y1+y2)/2 + label_dy}" class="dim-text">{label_str}</text>\n'
            return line + text

        x_spread = max_x - min_x
        y_spread = max_y - min_y
        
        if y_spread >= x_spread:
            label_x, label_y = "W", "L"
            label_tx, label_ty = "T", "U"
        else:
            label_x, label_y = "L", "W"
            label_tx, label_ty = "U", "T"

        off_b = -min_z + 28
        off_t = -max_z - 28
        off_l = min_x - 28

        side_svg += make_dim(min_x, off_b, max_x, off_b, label_x, 0, -12)
        side_svg += f'<line x1="{min_x}" y1="{-min_z}" x2="{min_x}" y2="{off_b}" class="dim-ext" />\n'
        side_svg += f'<line x1="{max_x}" y1="{-min_z}" x2="{max_x}" y2="{off_b}" class="dim-ext" />\n'
        
        side_svg += make_dim(min_tx, off_t, max_tx, off_t, label_tx, 0, 12)
        side_svg += f'<line x1="{min_tx}" y1="{-max_z}" x2="{min_tx}" y2="{off_t}" class="dim-ext" />\n'
        side_svg += f'<line x1="{max_tx}" y1="{-max_z}" x2="{max_tx}" y2="{off_t}" class="dim-ext" />\n'

        side_svg += make_dim(off_l, -girdle_z_top, off_l, -max_z, "C", -22, 0)
        side_svg += f'<line x1="{min_x}" y1="{-max_z}" x2="{off_l}" y2="{-max_z}" class="dim-ext" />\n'
        side_svg += f'<line x1="{min_x}" y1="{-girdle_z_top}" x2="{off_l}" y2="{-girdle_z_top}" class="dim-ext" />\n'

        side_svg += make_dim(off_l, -min_z, off_l, -girdle_z_bottom, "P", -22, 0)
        side_svg += f'<line x1="{min_x}" y1="{-min_z}" x2="{off_l}" y2="{-min_z}" class="dim-ext" />\n'
        side_svg += f'<line x1="{min_x}" y1="{-girdle_z_bottom}" x2="{off_l}" y2="{-girdle_z_bottom}" class="dim-ext" />\n'

        off_b_end = -min_z + 28
        off_t_end = -max_z - 28
        off_r = max_y + 28

        end_svg += make_dim(min_y, off_b_end, max_y, off_b_end, label_y, 0, -12)
        end_svg += f'<line x1="{min_y}" y1="{-min_z}" x2="{min_y}" y2="{off_b_end}" class="dim-ext" />\n'
        end_svg += f'<line x1="{max_y}" y1="{-min_z}" x2="{max_y}" y2="{off_b_end}" class="dim-ext" />\n'
        
        end_svg += make_dim(min_ty, off_t_end, max_ty, off_t_end, label_ty, 0, 12)
        end_svg += f'<line x1="{min_ty}" y1="{-max_z}" x2="{min_ty}" y2="{off_t_end}" class="dim-ext" />\n'
        end_svg += f'<line x1="{max_ty}" y1="{-max_z}" x2="{max_ty}" y2="{off_t_end}" class="dim-ext" />\n'

        end_svg += make_dim(off_r, -girdle_z_top, off_r, -max_z, "C", 22, 0)
        end_svg += f'<line x1="{max_y}" y1="{-max_z}" x2="{off_r}" y2="{-max_z}" class="dim-ext" />\n'
        end_svg += f'<line x1="{max_y}" y1="{-girdle_z_top}" x2="{off_r}" y2="{-girdle_z_top}" class="dim-ext" />\n'

        end_svg += make_dim(off_r, -min_z, off_r, -girdle_z_bottom, "P", 22, 0)
        end_svg += f'<line x1="{max_y}" y1="{-min_z}" x2="{off_r}" y2="{-min_z}" class="dim-ext" />\n'
        end_svg += f'<line x1="{max_y}" y1="{-girdle_z_bottom}" x2="{off_r}" y2="{-girdle_z_bottom}" class="dim-ext" />\n'

        crown_svg += '</g>\n'
        pav_svg += '</g>\n'
        side_svg += '</g>\n'
        
        end_svg += '  </g>\n</g>\n'

        return svg_header + crown_svg + pav_svg + side_svg + end_svg + "</svg>"

    def generate_dummy_svg(self, zoom=1.0) -> str:
        w = int(680 * zoom)
        h = int(720 * zoom)
        cx = int(340 * zoom)
        cy = int(360 * zoom)
        return f"""
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
            <g transform="translate({cx}, {cy})"><text text-anchor="middle" fill="#999">No diagram layout available.</text></g>
        </svg>
        """


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Faceting Diagram Viewer")
        self.resize(1400, 900)
        
        self.diagram_zoom = 1.0
        self.last_real_dims = {}
        self.selected_facet_name = None  
        self.selected_facet_section = None 
        self.window_3d = View3DWindow()

        info_group = QGroupBox("Design Information")
        info_grid = QGridLayout()
        self.lbl_title = QLabel("Title: -")
        self.lbl_filename = QLabel("File Name: -")
        self.lbl_gear = QLabel("Index Gear: -")
        self.lbl_ri = QLabel("RI: -")
        self.lbl_props = QLabel("L/W: -   T/W: -   U/W: -   P/W: -   C/W: -")
        
        style = "font-size: 13px;"
        props_style = "font-size: 13px; font-weight: bold; color: #1565c0;"
        for lbl in [self.lbl_title, self.lbl_filename, self.lbl_gear, self.lbl_ri]:
            lbl.setStyleSheet(style)
        self.lbl_props.setStyleSheet(props_style)

        self.target_l_input = QDoubleSpinBox()
        self.target_l_input.setRange(1.0, 100.0)
        self.target_l_input.setValue(10.0)
        self.target_l_input.setDecimals(1)
        self.target_l_input.setSuffix(" mm")
        self.target_l_input.setFixedWidth(100)
        self.target_l_input.valueChanged.connect(self.redraw_svg)
        
        self.lbl_calculated_dims = QLabel("W: - mm   H: - mm")
        self.lbl_calculated_dims.setStyleSheet("font-size: 13px; font-weight: bold; color: #c62828;")

        row3_layout = QHBoxLayout()
        row3_layout.addWidget(QLabel("Target L:"))
        row3_layout.addWidget(self.target_l_input)
        row3_layout.addSpacing(30)
        row3_layout.addWidget(self.lbl_calculated_dims)
        row3_layout.addStretch()

        self.open_button = QPushButton("Open ASC File")
        self.btn_save_asc = QPushButton("Save ASC File")
        self.btn_export_pdf = QPushButton("Export PDF")
        
        self.open_button.clicked.connect(self.open_file)
        self.btn_save_asc.clicked.connect(self.save_asc_file)
        self.btn_export_pdf.clicked.connect(self.export_pdf)

        self.chk_jamb_mode = QCheckBox("Jamb Peg Mode")
        self.chk_jamb_mode.setChecked(False)
        self.chk_jamb_mode.stateChanged.connect(self.on_mode_changed)

        row4_layout = QHBoxLayout()
        row4_layout.addWidget(self.chk_jamb_mode)
        row4_layout.addStretch()
        row4_layout.addWidget(self.open_button)
        row4_layout.addWidget(self.btn_save_asc)
        row4_layout.addWidget(self.btn_export_pdf)

        info_grid.addWidget(self.lbl_title, 0, 0)
        info_grid.addWidget(self.lbl_filename, 0, 1)
        info_grid.addWidget(self.lbl_gear, 1, 0)
        info_grid.addWidget(self.lbl_ri, 1, 1)
        info_grid.addWidget(self.lbl_props, 2, 0, 1, 2)
        info_grid.addLayout(row3_layout, 3, 0, 1, 2)
        info_grid.addLayout(row4_layout, 4, 0, 1, 2)
        info_group.setLayout(info_grid)

        self.crown_table = self.create_table()
        self.crown_table.itemChanged.connect(lambda item: self.on_table_item_changed(self.crown_table, item))
        self.crown_table.itemSelectionChanged.connect(lambda: self.on_table_selection(self.crown_table))
        crown_group = QGroupBox("Crown & Table")
        crown_layout = QVBoxLayout()
        crown_layout.addWidget(self.crown_table)
        crown_group.setLayout(crown_layout)

        self.pavilion_table = self.create_table()
        self.pavilion_table.itemChanged.connect(lambda item: self.on_table_item_changed(self.pavilion_table, item))
        self.pavilion_table.itemSelectionChanged.connect(lambda: self.on_table_selection(self.pavilion_table))
        pav_group = QGroupBox("Pavilion")
        pav_layout = QVBoxLayout()
        pav_layout.addWidget(self.pavilion_table)
        pav_group.setLayout(pav_layout)

        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(info_group)
        
        left_splitter = QSplitter(Qt.Vertical)
        left_splitter.addWidget(crown_group)
        left_splitter.addWidget(pav_group)
        left_splitter.setStretchFactor(0, 1)
        left_splitter.setStretchFactor(1, 1)
        left_layout.addWidget(left_splitter)

        self.drawing_group = QGroupBox("Diagram View")
        self.svg_widget = InteractiveSvgView()
        
        self.btn_zoom_out = QPushButton("-")
        self.btn_zoom_reset = QPushButton("Reset (Auto Fit)")
        self.btn_zoom_in = QPushButton("+")
        self.btn_3d_view = QPushButton("3D View")
        
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        self.btn_zoom_reset.clicked.connect(self.zoom_reset)
        self.btn_3d_view.clicked.connect(self.show_3d_window)
        
        for btn in [self.btn_zoom_out, self.btn_zoom_in]:
            btn.setFixedSize(30, 30)
            btn.setStyleSheet("font-weight: bold; background-color: #f0f0f0; border: 1px solid #ccc; border-radius: 3px;")
        self.btn_zoom_reset.setFixedSize(110, 30)
        self.btn_zoom_reset.setStyleSheet("font-weight: bold; background-color: #f0f0f0; border: 1px solid #ccc; border-radius: 3px;")
        self.btn_3d_view.setFixedSize(80, 30)
        self.btn_3d_view.setStyleSheet("font-weight: bold; color: white; background-color: #1976d2; border: 1px solid #1565c0; border-radius: 3px;")
            
        zoom_layout = QHBoxLayout()
        zoom_layout.addStretch()
        zoom_layout.addWidget(QLabel("Zoom:"))
        zoom_layout.addWidget(self.btn_zoom_out)
        zoom_layout.addWidget(self.btn_zoom_reset)
        zoom_layout.addWidget(self.btn_zoom_in)
        zoom_layout.addSpacing(20)
        zoom_layout.addWidget(self.btn_3d_view)

        drawing_layout = QVBoxLayout()
        drawing_layout.addWidget(self.svg_widget)
        drawing_layout.addLayout(zoom_layout)
        self.drawing_group.setLayout(drawing_layout)

        upper_splitter = QSplitter(Qt.Horizontal)
        upper_splitter.addWidget(left_container)
        upper_splitter.addWidget(self.drawing_group)
        upper_splitter.setStretchFactor(0, 1)
        upper_splitter.setStretchFactor(1, 0)

        main_layout = QVBoxLayout()
        main_layout.addWidget(upper_splitter)
        main_layout.setContentsMargins(8, 8, 8, 8) 

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def on_mode_changed(self):
        # ★ チェックボックス切り替え時に選択状態をリセット ★
        self.selected_facet_name = None
        self.selected_facet_section = None
        
        # テーブル側の選択状態も解除する（シグナルが発火しないようブロック）
        self.crown_table.blockSignals(True)
        self.crown_table.clearSelection()
        self.crown_table.blockSignals(False)
        
        self.pavilion_table.blockSignals(True)
        self.pavilion_table.clearSelection()
        self.pavilion_table.blockSignals(False)

        self.redraw_svg()
        self.refresh_tables()
        
    def on_table_selection(self, active_table):
        inactive_table = self.pavilion_table if active_table == self.crown_table else self.crown_table
        inactive_table.blockSignals(True)
        inactive_table.clearSelection()
        inactive_table.blockSignals(False)

        selected = active_table.selectedItems()
        if selected:
            row = selected[0].row()
            if hasattr(active_table, 'facet_mapping') and row < len(active_table.facet_mapping):
                facet = active_table.facet_mapping[row]
                self.selected_facet_name = facet.name
                self.selected_facet_section = facet.section 
        else:
            self.selected_facet_name = None
            self.selected_facet_section = None
            
        self.redraw_svg()

    def export_pdf(self):
        if getattr(self, 'current_diagram', None) is None:
            QMessageBox.warning(self, "Warning", "No diagram loaded.")
            return

        default_name = Path(self.current_file_path).stem + ".pdf" if hasattr(self, 'current_file_path') else "diagram.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF", default_name, "PDF Files (*.pdf)")
        if not path:
            return

        try:
            writer = QPdfWriter(path)
            writer.setPageSize(QPageSize(QPageSize.A4))
            writer.setPageOrientation(QPageLayout.Portrait)
            writer.setResolution(300)

            painter = QPainter(writer)
            painter.setRenderHint(QPainter.Antialiasing)

            margin = 150
            page_w = writer.width()
            page_h = writer.height()
            content_w = page_w - margin * 2

            y_pos = margin

            font_title = QFont("sans-serif", 16, QFont.Bold)
            font_normal = QFont("sans-serif", 12)
            font_bold = QFont("sans-serif", 12, QFont.Bold)

            painter.setFont(font_title)
            painter.drawText(margin, y_pos, self.lbl_title.text())
            y_pos += 80

            painter.setFont(font_normal)
            info_texts = [
                self.lbl_filename.text(),
                self.lbl_gear.text(),
                self.lbl_ri.text(),
                self.lbl_props.text(),
                self.lbl_calculated_dims.text()
            ]
            for text in info_texts:
                painter.drawText(margin, y_pos, text)
                y_pos += 60
            y_pos += 50

            renderer = SvgRenderer()
            generator = DiagramGenerator()
            polygons = generator.generate_polygons(self.current_diagram)
            svg_data = renderer.generate_svg(
                self.current_diagram, polygons, self.last_real_dims, 
                self.chk_jamb_mode.isChecked(), zoom=1.0, 
                selected_facet_name=None, selected_facet_section=None
            )
            svg_renderer = QSvgRenderer(QByteArray(svg_data.encode('utf-8')))
            
            svg_rect_w = content_w
            svg_rect_h = int(svg_rect_w * (720 / 680))
            if svg_rect_h > 1800:
                svg_rect_h = 1800
                svg_rect_w = int(1800 * (680 / 720))

            svg_x = margin + (content_w - svg_rect_w) // 2
            svg_renderer.render(painter, QRectF(svg_x, y_pos, svg_rect_w, svg_rect_h))
            y_pos += svg_rect_h + 100

            def draw_pdf_table(title, table_widget):
                nonlocal y_pos
                if y_pos > page_h - 400:
                    writer.newPage()
                    y_pos = margin

                painter.setFont(font_title)
                painter.drawText(margin, y_pos, title)
                y_pos += 60

                painter.setFont(font_bold)
                cols = table_widget.columnCount()
                rows = table_widget.rowCount()
                
                visible_cols = [c for c in range(cols) if not table_widget.isColumnHidden(c)]
                
                weight_map = {0: 1.0, 1: 1.5, 2: 2.5, 3: 4.5, 4: 3.0}
                total_weight = sum(weight_map[c] for c in visible_cols)
                
                col_widths = {c: (content_w * weight_map[c]) / total_weight for c in visible_cols}
                
                row_h = 60
                
                curr_x = margin
                for c in visible_cols:
                    rect = QRectF(curr_x, y_pos, col_widths[c], row_h)
                    painter.drawRect(rect)
                    painter.drawText(rect, Qt.AlignCenter, table_widget.horizontalHeaderItem(c).text())
                    curr_x += col_widths[c]
                y_pos += row_h
                painter.setFont(font_normal)

                for r in range(rows):
                    if y_pos > page_h - margin - row_h:
                        writer.newPage()
                        y_pos = margin
                        painter.setFont(font_bold)
                        curr_x = margin
                        for c in visible_cols:
                            rect = QRectF(curr_x, y_pos, col_widths[c], row_h)
                            painter.drawRect(rect)
                            painter.drawText(rect, Qt.AlignCenter, table_widget.horizontalHeaderItem(c).text())
                            curr_x += col_widths[c]
                        y_pos += row_h
                        painter.setFont(font_normal)

                    curr_x = margin
                    for c in visible_cols:
                        item = table_widget.item(r, c)
                        text = item.text() if item else ""
                        rect = QRectF(curr_x, y_pos, col_widths[c], row_h)
                        painter.drawRect(rect)
                        
                        if c == 4:
                            text_rect = QRectF(curr_x + 20, y_pos, col_widths[c] - 40, row_h)
                            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
                        else:
                            painter.drawText(rect, Qt.AlignCenter, text)
                        curr_x += col_widths[c]
                    y_pos += row_h
                y_pos += 100

            draw_pdf_table("Crown & Table", self.crown_table)
            draw_pdf_table("Pavilion", self.pavilion_table)

            painter.end()
            QMessageBox.information(self, "Success", "PDF exported successfully.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export PDF:\n{str(e)}")

    def on_table_item_changed(self, table, item):
        if item.column() == 4:
            row = item.row()
            if hasattr(table, 'facet_mapping') and row < len(table.facet_mapping):
                facet = table.facet_mapping[row]
                facet.instruction = item.text()

    def save_asc_file(self):
        if not hasattr(self, 'original_asc_lines') or not hasattr(self, 'current_diagram'):
            QMessageBox.warning(self, "Warning", "No ASC file loaded.")
            return
            
        default_path = getattr(self, 'current_file_path', "")
        save_path, _ = QFileDialog.getSaveFileName(self, "Save ASC File", default_path, "ASC Files (*.asc);;All Files (*)")
        
        if not save_path:
            return
            
        try:
            new_lines = []
            facet_idx = 0
            
            for line in self.original_asc_lines:
                if line.startswith('a '):
                    if facet_idx < len(self.current_diagram.facets):
                        facet = self.current_diagram.facets[facet_idx]
                        tokens = line.strip().split()
                        
                        last_n_idx = -1
                        for i in range(len(tokens)-1, -1, -1):
                            if tokens[i] == 'n':
                                last_n_idx = i
                                break
                        
                        if last_n_idx != -1 and last_n_idx + 1 < len(tokens):
                            name_token = tokens[last_n_idx+1]
                            pattern = r'(.*\bn\s+' + re.escape(name_token) + r')'
                            match = re.search(pattern, line)
                            
                            if match:
                                base_str = match.group(1)
                                inst = getattr(facet, 'instruction', '').strip()
                                if inst:
                                    new_line = base_str + " " + inst + "\n"
                                else:
                                    new_line = base_str + "\n"
                                new_lines.append(new_line)
                            else:
                                new_lines.append(line)
                        else:
                            new_lines.append(line)
                        
                        facet_idx += 1
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)
                    
            with open(save_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
                
            self.original_asc_lines = new_lines
            self.current_file_path = save_path
            QMessageBox.information(self, "Success", "ASC file saved successfully.")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save ASC file:\n{str(e)}")

    def show_3d_window(self):
        self.window_3d.show()
        self.window_3d.raise_()

    def zoom_in(self):
        self.diagram_zoom *= 1.25
        self.redraw_svg()
        
    def zoom_out(self):
        self.diagram_zoom /= 1.25
        if self.diagram_zoom < 0.2:
            self.diagram_zoom = 0.2
        self.redraw_svg()
        
    def zoom_reset(self):
        view_w = self.svg_widget.viewport().width()
        view_h = self.svg_widget.viewport().height()
        target_w = view_w - 20
        target_h = view_h - 20
        if target_w > 0 and target_h > 0:
            zoom_w = target_w / 680.0
            zoom_h = target_h / 720.0
            self.diagram_zoom = min(zoom_w, zoom_h)
        else:
            self.diagram_zoom = 1.0
        self.redraw_svg()

    def resizeEvent(self, event):
        if hasattr(self, 'drawing_group'):
            self.drawing_group.setFixedWidth(int(self.width() * 0.5))
        super().resizeEvent(event)

    def create_table(self):
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Facet", "Angle", "Jamb Peg", "Index", "Instruction"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        return table

    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open ASC File", "", "ASC Files (*.asc);;All Files (*)")
        if file_path:
            self.current_file_path = file_path
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                self.original_asc_lines = f.readlines()
                
            p = Path(file_path)
            diagram = load_asc(str(p))
            
            extracted_title = ""
            for line in self.original_asc_lines:
                if line.startswith('H '):
                    text = line[2:].strip()
                    if text and not text.startswith('(') and ':' not in text and 'Unpublished' not in text and 'Calculations' not in text:
                        extracted_title = text
                        break
            
            if extracted_title:
                diagram.title = extracted_title
            elif not diagram.title:
                diagram.title = p.name
                
            self.update_ui(diagram)

    def update_ui(self, diagram):
        self.current_diagram = diagram
        
        self.selected_facet_name = None
        self.selected_facet_section = None
        
        self.lbl_title.setText(f"Title: {diagram.title}")
        
        if hasattr(self, 'current_file_path'):
            self.lbl_filename.setText(f"File Name: {Path(self.current_file_path).name}")
        else:
            self.lbl_filename.setText("File Name: -")
        
        gear = getattr(diagram, 'index_gear', 64)
        if gear <= 0: gear = 64
        self.lbl_gear.setText(f"Index Gear: {gear}")
        
        ri_val = getattr(diagram, 'ri', None) or (diagram.ri_value if hasattr(diagram, 'ri_value') else "1.54")
        self.lbl_ri.setText(f"RI (Refractive Index): {ri_val}")

        is_valid_jamb_gear = (gear == 64 or gear == 48)
        
        self.chk_jamb_mode.blockSignals(True)
        if not is_valid_jamb_gear:
            self.chk_jamb_mode.setChecked(False)
        self.chk_jamb_mode.setEnabled(is_valid_jamb_gear)
        self.chk_jamb_mode.blockSignals(False)

        self.pav_facets = [f for f in diagram.facets if f.section in ["Pavilion", "Girdle"]]
        self.tab_facets = [f for f in diagram.facets if f.section == "Table"]
        self.crown_facets = [f for f in diagram.facets if f.section == "Crown"]

        self.refresh_tables()
        self.zoom_reset()
        
    def refresh_tables(self):
        if getattr(self, 'current_diagram', None) is None:
            return
        self.populate_table(self.crown_table, self.crown_facets + self.tab_facets)
        self.populate_table(self.pavilion_table, self.pav_facets)

    def redraw_svg(self):
        if getattr(self, 'current_diagram', None) is None:
            return
            
        generator = DiagramGenerator()
        polygons = generator.generate_polygons(self.current_diagram)
        
        show_jamb = self.chk_jamb_mode.isChecked()
        self.window_3d.update_3d_view(polygons, show_jamb)
        
        real_dims = {}
        if polygons:
            try:
                all_pts = np.vstack([p['points'] for p in polygons])
                xs, ys, zs = all_pts[:, 0], all_pts[:, 1], all_pts[:, 2]
                
                x_spread = np.max(xs) - np.min(xs)
                y_spread = np.max(ys) - np.min(ys)
                
                if y_spread >= x_spread:
                    base_L = y_spread
                    base_W = x_spread
                    
                    table_pts = [p['points'] for p in polygons if p['facet'].section == 'Table']
                    if table_pts:
                        t_pts = np.vstack(table_pts)
                        base_U = np.max(t_pts[:, 1]) - np.min(t_pts[:, 1])
                        base_T = np.max(t_pts[:, 0]) - np.min(t_pts[:, 0])
                    else:
                        base_U, base_T = 0.0, 0.0
                else:
                    base_L = x_spread
                    base_W = y_spread
                    
                    table_pts = [p['points'] for p in polygons if p['facet'].section == 'Table']
                    if table_pts:
                        t_pts = np.vstack(table_pts)
                        base_U = np.max(t_pts[:, 0]) - np.min(t_pts[:, 0])
                        base_T = np.max(t_pts[:, 1]) - np.min(t_pts[:, 1])
                    else:
                        base_U, base_T = 0.0, 0.0
                
                if base_W < 1e-6: base_W = 1.0

                crown_pts = [p['points'] for p in polygons if p['facet'].section in ['Crown', 'Table']]
                girdle_z_top = np.min(np.vstack(crown_pts)[:, 2]) if crown_pts else 0.0
                
                pav_pts = [p['points'] for p in polygons if p['facet'].section == 'Pavilion']
                girdle_z_bottom = np.max(np.vstack(pav_pts)[:, 2]) if pav_pts else 0.0

                base_C = np.max(zs) - girdle_z_top
                base_P = girdle_z_bottom - np.min(zs)

                lw, tw, uw, pw, cw = base_L/base_W, base_T/base_W, base_U/base_W, base_P/base_W, base_C/base_W
                self.lbl_props.setText(f"L/W = {lw:.3f}   T/W = {tw:.3f}   U/W = {uw:.3f}   P/W = {pw:.3f}   C/W = {cw:.3f}")
                
                target_L = self.target_l_input.value()
                real_scale = target_L / base_L if base_L > 1e-6 else 1.0
                
                real_w = base_W * real_scale
                real_c = base_C * real_scale
                real_p = base_P * real_scale
                
                real_h = real_c + real_p + 0.2
                
                self.lbl_calculated_dims.setText(f"W: {real_w:.2f} mm   |   H (incl. 0.2mm girdle): {real_h:.2f} mm")
                
                real_dims = {
                    'L': target_L,
                    'W': real_w,
                    'T': base_T * real_scale,
                    'U': base_U * real_scale,
                    'C': real_c,
                    'P': real_p
                }
                
            except Exception as e:
                self.lbl_props.setText("L/W: Error  T/W: Error  U/W: Error  P/W: Error  C/W: Error")
                self.lbl_calculated_dims.setText("W: Error   H: Error")

        self.last_real_dims = real_dims

        renderer = SvgRenderer()
        svg_data = renderer.generate_svg(
            self.current_diagram, polygons, real_dims, show_jamb, 
            zoom=self.diagram_zoom, 
            selected_facet_name=self.selected_facet_name,
            selected_facet_section=self.selected_facet_section
        )
        self.svg_widget.load(QByteArray(svg_data.encode('utf-8')))

    def populate_table(self, table, facets):
        table.blockSignals(True)
        table.clearContents()
        
        facets = sorted(facets, key=lambda f: f.id)
        table.facet_mapping = facets 
        table.setRowCount(len(facets))
        
        gear = getattr(self.current_diagram, 'index_gear', 64)
        if gear <= 0: gear = 64
        is_valid_jamb_gear = (gear == 64 or gear == 48)
        
        show_jamb_mode = self.chk_jamb_mode.isChecked()
        
        for row, facet in enumerate(facets):
            item_name = QTableWidgetItem(facet.name)
            item_name.setTextAlignment(Qt.AlignCenter)
            item_name.setFlags(item_name.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 0, item_name)
            
            if show_jamb_mode:
                display_angle = 90.0 - abs(facet.angle)
            else:
                display_angle = abs(facet.angle)
            item_angle = QTableWidgetItem(f"{display_angle:.2f}°")
            item_angle.setTextAlignment(Qt.AlignCenter)
            item_angle.setFlags(item_angle.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 1, item_angle)
            
            if is_valid_jamb_gear:
                jamb_str = " ".join(facet.index.jamb)
            else:
                jamb_str = ""
            item_jamb = QTableWidgetItem(jamb_str)
            item_jamb.setTextAlignment(Qt.AlignCenter)
            item_jamb.setFlags(item_jamb.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 2, item_jamb)
            
            raw_list = getattr(facet, 'raw_indices', [])
            if not raw_list and hasattr(facet, 'index') and facet.index.original:
                raw_list = facet.index.original
            
            if facet.name == "T" or facet.section == "Table":
                idx_str = "Table"
            else:
                mapped_list = []
                for i in raw_list:
                    val = gear if i == 0 else i
                    if isinstance(val, float) and val.is_integer():
                        mapped_list.append(int(val))
                    else:
                        mapped_list.append(val)
                mapped_list.sort(key=lambda x: 0 if x == gear else x)
                idx_str = "-".join(str(i) for i in mapped_list)
            
            item_idx = QTableWidgetItem(idx_str)
            item_idx.setTextAlignment(Qt.AlignCenter)
            item_idx.setFlags(item_idx.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 3, item_idx)
            
            item_inst = QTableWidgetItem(getattr(facet, 'instruction', ''))
            item_inst.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 4, item_inst)
            
        table.setColumnHidden(2, not show_jamb_mode)
        table.setColumnHidden(3, show_jamb_mode)
            
        table.resizeColumnsToContents() 
        table.setColumnWidth(0, 60)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        table.setColumnWidth(1, 70)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(False) 
        
        table.blockSignals(False)