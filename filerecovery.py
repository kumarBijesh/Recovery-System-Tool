import sys
import os
import psutil
import shutil
import time
from datetime import datetime
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel, QVBoxLayout, QTextEdit, QFileDialog,
    QGridLayout, QComboBox, QProgressBar, QTabWidget, QSizePolicy, QMessageBox,
    QHBoxLayout, QGroupBox
)
from PyQt5.QtGui import QFont, QIcon, QColor
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import pyqtgraph as pg

# Custom Thread for Scanning Files
class FileScannerThread(QThread):
    update_progress = pyqtSignal(int, int, int)  # progress, scanned_files, total_files
    scan_result = pyqtSignal(list)  # list of file details
    file_count = pyqtSignal(int)    # total file count

    def __init__(self, drive_path):
        super().__init__()
        self.drive_path = drive_path

    def run(self):
        files_info = []
        total_files = 0
        scanned_files = 0

        # Count files in a single pass
        for root, _, files in os.walk(self.drive_path, onerror=lambda err: None):
            total_files += len(files)
        self.file_count.emit(total_files)

        # Scan files
        for root, _, files in os.walk(self.drive_path, onerror=lambda err: None):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    file_stat = os.stat(file_path)
                    last_access_time = file_stat.st_atime
                    last_modified_time = file_stat.st_mtime
                    days_unused = (time.time() - last_access_time) / (24 * 3600)
                    size = file_stat.st_size / (1024 * 1024)  # Size in MB

                    # Get owner (cross-platform fallback)
                    try:
                        import pwd
                        owner_name = pwd.getpwuid(file_stat.st_uid).pw_name
                    except:
                        owner_name = "Unknown"

                    files_info.append({
                        "path": file_path,
                        "name": file,
                        "size_mb": size,
                        "last_accessed": datetime.fromtimestamp(last_access_time).strftime("%Y-%m-%d %H:%M:%S"),
                        "last_modified": datetime.fromtimestamp(last_modified_time).strftime("%Y-%m-%d %H:%M:%S"),
                        "days_unused": days_unused,
                        "owner": owner_name,
                        "access_timestamp": last_access_time,
                        "mod_timestamp": last_modified_time
                    })
                except Exception as e:
                    print(f"Error accessing {file_path}: {e}")

                scanned_files += 1
                if total_files > 0:
                    progress = int((scanned_files / total_files) * 100)
                    self.update_progress.emit(progress, scanned_files, total_files)

        self.scan_result.emit(files_info)

# Enhanced File Event Handler for Monitoring
class FileEventHandler(FileSystemEventHandler):
    def __init__(self, update_signal):
        super().__init__()
        self.update_signal = update_signal
        self.file_events = {'created': 0, 'modified': 0, 'deleted': 0, 'moved': 0}

    def on_created(self, event):
        if not event.is_directory:
            self.file_events['created'] += 1
            self.update_signal.emit('created', event.src_path, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def on_modified(self, event):
        if not event.is_directory:
            self.file_events['modified'] += 1
            self.update_signal.emit('modified', event.src_path, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def on_deleted(self, event):
        if not event.is_directory:
            self.file_events['deleted'] += 1
            self.update_signal.emit('deleted', event.src_path, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def on_moved(self, event):
        if not event.is_directory:
            self.file_events['moved'] += 1
            self.update_signal.emit('moved', f"{event.src_path} → {event.dest_path}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

# Main Application Window
class FileSystemTool(QWidget):
    def __init__(self):
        super().__init__()
        self.folder_to_monitor = None
        self.observer = None
        self.scanner_thread = None
        self.file_events = {'created': 0, 'modified': 0, 'deleted': 0, 'moved': 0}
        self.scanned_files = []
        self.initUI()

    def initUI(self):
        self.setWindowTitle("File System Recovery & Optimization Tool")
        self.setGeometry(100, 100, 1280, 720)
        self.setStyleSheet("""
            QWidget {
                background-color: #1E1E2E;
                color: #CDD6F4;
                font-family: 'Segoe UI', Arial;
            }
            QPushButton {
                background-color: #585B70;
                color: #CDD6F4;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 14px;
                border: none;
            }
            QPushButton:hover {
                background-color: #89B4FA;
            }
            QTextEdit {
                background-color: #181825;
                color: #CDD6F4;
                border: 1px solid #313244;
                padding: 8px;
                border-radius: 4px;
                font-size: 12px;
            }
            QComboBox {
                background-color: #585B70;
                color: #CDD6F4;
                padding: 6px;
                border-radius: 4px;
                font-size: 14px;
            }
            QProgressBar {
                background-color: #313244;
                color: #CDD6F4;
                border-radius: 4px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #89B4FA;
                border-radius: 4px;
            }
            QLabel {
                font-size: 14px;
                color: #CDD6F4;
            }
            QGroupBox {
                border: 1px solid #313244;
                border-radius: 4px;
                margin-top: 12px;
                padding: 10px;
                color: #CDD6F4;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                color: #CDD6F4;
            }
            QTabWidget::pane {
                border: 1px solid #313244;
                background: #1E1E2E;
            }
            QTabBar::tab {
                background: #313244;
                color: #CDD6F4;
                padding: 8px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #89B4FA;
                color: #1E1E2E;
            }
        """)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # Title
        title = QLabel("📂 File System Recovery & Optimization Tool")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setFont(QFont("Segoe UI", 12))
        main_layout.addWidget(self.tabs)

        # File Operations Tab
        file_operations_tab = QWidget()
        file_operations_layout = QVBoxLayout()
        file_operations_layout.setSpacing(12)

        # Drive Selector
        self.drive_selector = QComboBox()
        self.drive_selector.addItem("Select a Drive")
        self.drive_selector.currentIndexChanged.connect(self.display_drive_files)
        file_operations_layout.addWidget(self.drive_selector)

        # File Count Label
        self.file_count_label = QLabel("Total files: 0")
        self.file_count_label.setFont(QFont("Segoe UI", 12))
        file_operations_layout.addWidget(self.file_count_label)

        # Buttons
        button_layout = QGridLayout()
        button_layout.setSpacing(8)
        buttons = {
            "📁 Scan System": self.scan_files,
            "👀 Monitor Files": self.start_monitoring,
            "🔄 Recover Files": self.recover_deleted_files,
            "⚙️ Optimize Storage": self.optimize_storage,
            "📂 Select Folder": self.select_folder,
            "🧹 Clear Log": self.clear_output
        }

        row, col = 0, 0
        for text, function in buttons.items():
            btn = QPushButton(text)
            btn.setFont(QFont("Segoe UI", 12))
            btn.clicked.connect(function)
            btn.setToolTip(f"Click to {text.lower()}")
            button_layout.addWidget(btn, row, col)
            col += 1
            if col > 2:
                col = 0
                row += 1

        file_operations_layout.addLayout(button_layout)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        file_operations_layout.addWidget(self.progress_bar)

        # Output Log
        self.output_text = QTextEdit(readOnly=True)
        self.output_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        file_operations_layout.addWidget(self.output_text)

        file_operations_tab.setLayout(file_operations_layout)
        self.tabs.addTab(file_operations_tab, "File Operations")

        # System Info Tab
        system_info_tab = QWidget()
        system_info_layout = QVBoxLayout()
        system_info_layout.setSpacing(12)

        # System Info Label
        system_info_label = QLabel("🖥️ System Information")
        system_info_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        system_info_layout.addWidget(system_info_label)

        # CPU Usage
        self.cpu_usage_label = QLabel("💻 CPU Usage: 0%")
        self.cpu_usage_label.setFont(QFont("Segoe UI", 14))
        system_info_layout.addWidget(self.cpu_usage_label)

        # CPU Usage Graph
        self.cpu_graph = pg.PlotWidget(title="CPU Usage (%)")
        self.cpu_graph.setBackground("#181825")
        self.cpu_graph.setYRange(0, 100)
        self.cpu_graph.showGrid(x=True, y=True)
        self.cpu_curve = self.cpu_graph.plot(pen=pg.mkPen(color="#89B4FA", width=2))
        system_info_layout.addWidget(self.cpu_graph)

        # Memory Usage
        self.memory_usage_label = QLabel("🧠 Memory Usage: 0%")
        self.memory_usage_label.setFont(QFont("Segoe UI", 14))
        system_info_layout.addWidget(self.memory_usage_label)

        # Memory Usage Graph
        self.memory_graph = pg.PlotWidget(title="Memory Usage (%)")
        self.memory_graph.setBackground("#181825")
        self.memory_graph.setYRange(0, 100)
        self.memory_graph.showGrid(x=True, y=True)
        self.memory_curve = self.memory_graph.plot(pen=pg.mkPen(color="#F38BA8", width=2))
        system_info_layout.addWidget(self.memory_graph)

        system_info_tab.setLayout(system_info_layout)
        self.tabs.addTab(system_info_tab, "System Info")

        # File Stats Tab
        file_stats_tab = QWidget()
        file_stats_layout = QVBoxLayout()
        file_stats_layout.setSpacing(12)

        # File Stats Label
        file_stats_label = QLabel("📊 File Statistics")
        file_stats_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        file_stats_layout.addWidget(file_stats_label)

        # Access/Modification Graphs
        graph_group = QGroupBox("File Access Patterns")
        graph_layout = QHBoxLayout()

        # Last Access Graph
        self.access_graph = pg.PlotWidget(title="Last Access Time Distribution")
        self.access_graph.setBackground("#181825")
        self.access_graph.showGrid(x=True, y=True)
        self.access_graph.setLabel('left', "Number of Files")
        self.access_graph.setLabel('bottom', "Days Since Access")
        graph_layout.addWidget(self.access_graph)

        # Last Modification Graph
        self.mod_graph = pg.PlotWidget(title="Last Modification Time Distribution")
        self.mod_graph.setBackground("#181825")
        self.mod_graph.showGrid(x=True, y=True)
        self.mod_graph.setLabel('left', "Number of Files")
        self.mod_graph.setLabel('bottom', "Days Since Modification")
        graph_layout.addWidget(self.mod_graph)

        graph_group.setLayout(graph_layout)
        file_stats_layout.addWidget(graph_group)

        # Top Files Group
        top_files_group = QGroupBox("Top Files")
        top_files_layout = QHBoxLayout()

        # Most Accessed Files
        self.most_accessed_graph = pg.PlotWidget(title="Recently Accessed Files")
        self.most_accessed_graph.setBackground("#181825")
        self.most_accessed_graph.showGrid(x=True, y=True)
        self.most_accessed_graph.setLabel('left', "Days Since Access")
        self.most_accessed_graph.setLabel('bottom', "File Name")
        top_files_layout.addWidget(self.most_accessed_graph)

        # Most Modified Files
        self.most_modified_graph = pg.PlotWidget(title="Recently Modified Files")
        self.most_modified_graph.setBackground("#181825")
        self.most_modified_graph.showGrid(x=True, y=True)
        self.most_modified_graph.setLabel('left', "Days Since Modification")
        self.most_modified_graph.setLabel('bottom', "File Name")
        top_files_layout.addWidget(self.most_modified_graph)

        top_files_group.setLayout(top_files_layout)
        file_stats_layout.addWidget(top_files_group)

        file_stats_tab.setLayout(file_stats_layout)
        self.tabs.addTab(file_stats_tab, "File Stats")

        # File Monitoring Tab
        monitor_tab = QWidget()
        monitor_layout = QVBoxLayout()
        monitor_layout.setSpacing(12)

        # Monitoring Label
        monitor_label = QLabel("👀 File Monitoring")
        monitor_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        monitor_layout.addWidget(monitor_label)

        # Monitoring Controls
        monitor_controls = QHBoxLayout()
        self.start_monitor_btn = QPushButton("Start Monitoring")
        self.start_monitor_btn.clicked.connect(self.start_monitoring)
        self.stop_monitor_btn = QPushButton("Stop Monitoring")
        self.stop_monitor_btn.clicked.connect(self.stop_monitoring)
        self.stop_monitor_btn.setEnabled(False)
        monitor_controls.addWidget(self.start_monitor_btn)
        monitor_controls.addWidget(self.stop_monitor_btn)
        monitor_layout.addLayout(monitor_controls)

        # Current Monitoring Folder
        self.monitoring_folder_label = QLabel("No folder selected for monitoring")
        self.monitoring_folder_label.setFont(QFont("Segoe UI", 12))
        monitor_layout.addWidget(self.monitoring_folder_label)

        # Monitoring Stats
        monitor_stats_group = QGroupBox("Monitoring Statistics")
        monitor_stats_layout = QVBoxLayout()

        # File Events Graph
        self.file_events_graph = pg.PlotWidget(title="File Events Count")
        self.file_events_graph.setBackground("#181825")
        self.file_events_graph.showGrid(x=True, y=True)
        self.file_events_graph.setLabel('left', "Count")
        self.file_events_graph.setLabel('bottom', "Event Type")
        monitor_stats_layout.addWidget(self.file_events_graph)

        monitor_stats_group.setLayout(monitor_stats_layout)
        monitor_layout.addWidget(monitor_stats_group)

        # Monitoring Log
        self.monitor_log = QTextEdit(readOnly=True)
        self.monitor_log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        monitor_layout.addWidget(self.monitor_log)

        monitor_tab.setLayout(monitor_layout)
        self.tabs.addTab(monitor_tab, "Monitoring")

        self.setLayout(main_layout)
        self.load_drives()

        # Initialize data for graphs
        self.cpu_data = []
        self.memory_data = []
        self.time_data = []

        # Start real-time system info updates
        self.system_info_timer = QTimer()
        self.system_info_timer.timeout.connect(self.update_system_info)
        self.system_info_timer.start(2000)  # Update every 2 seconds

    def load_drives(self):
        self.drive_selector.clear()
        self.drive_selector.addItem("Select a Drive")
        for drive in [d.mountpoint for d in psutil.disk_partitions() if os.access(d.mountpoint, os.R_OK)]:
            self.drive_selector.addItem(drive)

    def display_drive_files(self):
        selected_drive = self.drive_selector.currentText()
        if selected_drive == "Select a Drive":
            return

        self.output_text.append(f"📂 Files in {selected_drive}:\n")
        file_count = 0
        try:
            for root, _, files in os.walk(selected_drive, onerror=lambda err: None):
                for file in files[:10]:
                    file_path = os.path.join(root, file)
                    try:
                        size = os.path.getsize(file_path) / (1024 * 1024)
                        last_access = datetime.fromtimestamp(os.path.getatime(file_path)).strftime("%Y-%m-%d %H:%M:%S")
                        last_mod = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime("%Y-%m-%d %H:%M:%S")
                        self.output_text.append(f"📄 {file_path}\n   Size: {size:.2f} MB\n   Last Access: {last_access}\n   Last Modified: {last_mod}\n")
                        file_count += 1
                    except Exception as e:
                        self.output_text.append(f"❌ Error reading {file_path}: {e}")
        except Exception as e:
            self.output_text.append(f"❌ Error accessing drive {selected_drive}: {e}")

        self.file_count_label.setText(f"Total files in drive: {file_count} (sample)")

    def scan_files(self):
        selected_drive = self.drive_selector.currentText()
        if selected_drive == "Select a Drive":
            QMessageBox.warning(self, "Warning", "Please select a drive first!")
            return

        self.output_text.append("🔍 Scanning file system...\n")
        self.progress_bar.setValue(0)

        self.scanner_thread = FileScannerThread(selected_drive)
        self.scanner_thread.update_progress.connect(self.update_progress)
        self.scanner_thread.scan_result.connect(self.display_scan_results)
        self.scanner_thread.file_count.connect(self.update_file_count)
        self.scanner_thread.start()

    def update_file_count(self, count):
        self.file_count_label.setText(f"Total files found: {count}")

    def update_progress(self, progress, scanned_files, total_files):
        self.progress_bar.setValue(progress)
        self.output_text.append(f"📊 Progress: {scanned_files}/{total_files} files scanned ({progress}%)")

    def display_scan_results(self, files):
        self.scanned_files = files
        if files:
            self.output_text.append(f"✅ Scan complete! Found {len(files)} files.\n")
            self.output_text.append("⚠️ Unused Files (Not accessed for >180 days):\n")
            for file in files[:20]:
                if file['days_unused'] > 180:
                    self.output_text.append(
                        f"📄 File: {file['name']}\n"
                        f"   📂 Path: {file['path']}\n"
                        f"   👤 Owner: {file['owner']}\n"
                        f"   📦 Size: {file['size_mb']:.2f} MB\n"
                        f"   🕒 Last Accessed: {file['last_accessed']}\n"
                        f"   🕒 Last Modified: {file['last_modified']}\n"
                        f"   🕒 Days Unused: {file['days_unused']:.1f}\n"
                        "----------------------------------------\n"
                    )
            self.update_file_statistics(files)
        else:
            self.output_text.append("✅ No unused files found.\n")

    def update_file_statistics(self, files):
        if not files:
            return

        now = time.time()
        access_days = [(now - f['access_timestamp']) / (24 * 3600) for f in files if f['access_timestamp']]
        mod_days = [(now - f['mod_timestamp']) / (24 * 3600) for f in files if f['mod_timestamp']]

        # Create histograms
        max_days = 365 * 2
        access_counts, access_bins = np.histogram(access_days, bins=20, range=(0, max_days))
        mod_counts, mod_bins = np.histogram(mod_days, bins=20, range=(0, max_days))

        # Plot last access distribution
        self.access_graph.clear()
        bg1 = pg.BarGraphItem(x=access_bins[:-1], height=access_counts, width=access_bins[1]-access_bins[0], brush="#89B4FA")
        self.access_graph.addItem(bg1)

        # Plot last modification distribution
        self.mod_graph.clear()
        bg2 = pg.BarGraphItem(x=mod_bins[:-1], height=mod_counts, width=mod_bins[1]-mod_bins[0], brush="#F38BA8")
        self.mod_graph.addItem(bg2)

        # Get top 10 most recently accessed and modified files
        top_accessed = sorted(files, key=lambda x: x['access_timestamp'], reverse=True)[:10]
        top_modified = sorted(files, key=lambda x: x['mod_timestamp'], reverse=True)[:10]

        # Plot most accessed files
        self.most_accessed_graph.clear()
        x = range(len(top_accessed))
        y = [(now - f['access_timestamp']) / (24 * 3600) for f in top_accessed]
        names = [f['name'][:12] + '...' if len(f['name']) > 12 else f['name'] for f in top_accessed]
        bg3 = pg.BarGraphItem(x=x, height=y, width=0.4, brush="#A6E3A1")
        self.most_accessed_graph.addItem(bg3)
        axis = self.most_accessed_graph.getAxis('bottom')
        axis.setTicks([[(i, names[i]) for i in range(len(names))]])

        # Plot most modified files
        self.most_modified_graph.clear()
        y = [(now - f['mod_timestamp']) / (24 * 3600) for f in top_modified]
        names = [f['name'][:12] + '...' if len(f['name']) > 12 else f['name'] for f in top_modified]
        bg4 = pg.BarGraphItem(x=x, height=y, width=0.4, brush="#F9E2AF")
        self.most_modified_graph.addItem(bg4)
        axis = self.most_modified_graph.getAxis('bottom')
        axis.setTicks([[(i, names[i]) for i in range(len(names))]])

    def start_monitoring(self):
        if not self.folder_to_monitor:
            QMessageBox.warning(self, "Warning", "Please select a folder first!")
            return

        if hasattr(self, 'observer') and self.observer:
            self.stop_monitoring()

        self.monitor_log.append(f"🟢 Starting monitoring on: {self.folder_to_monitor}")
        self.monitoring_folder_label.setText(f"Monitoring folder: {self.folder_to_monitor}")

        # Reset file events counter
        self.file_events = {'created': 0, 'modified': 0, 'deleted': 0, 'moved': 0}

        # Create observer and event handler
        self.observer = Observer()
        event_handler = FileEventHandler(self.update_monitor_log)
        self.observer.schedule(event_handler, self.folder_to_monitor, recursive=True)
        
        try:
            self.observer.start()
            self.start_monitor_btn.setEnabled(False)
            self.stop_monitor_btn.setEnabled(True)
            
            # Start timer for updating stats if not already running
            if not hasattr(self, 'monitor_timer') or not self.monitor_timer.isActive():
                self.monitor_timer = QTimer()
                self.monitor_timer.timeout.connect(self.update_monitor_stats)
                self.monitor_timer.start(2000)  # Update every 2 seconds
                
        except Exception as e:
            self.monitor_log.append(f"❌ Failed to start monitoring: {str(e)}")
            if self.observer:
                self.observer.stop()
                self.observer = None

    def stop_monitoring(self):
        if hasattr(self, 'observer') and self.observer:
            try:
                self.observer.stop()
                self.observer.join()
                self.monitor_log.append("🔴 Monitoring stopped")
            except Exception as e:
                self.monitor_log.append(f"❌ Error stopping monitoring: {str(e)}")
            finally:
                self.observer = None

        if hasattr(self, 'monitor_timer') and self.monitor_timer.isActive():
            self.monitor_timer.stop()

        self.start_monitor_btn.setEnabled(True)
        self.stop_monitor_btn.setEnabled(False)

    def update_monitor_log(self, event_type, path, timestamp):
        colors = {
            'created': '#A6E3A1',
            'modified': '#F9E2AF',
            'deleted': '#F38BA8',
            'moved': '#89B4FA'
        }
        
        # Update the log with colored text
        self.monitor_log.append(
            f"<span style='color:{colors[event_type]}'>"
            f"🕒 {timestamp} - {event_type.upper()}: {path}"
            f"</span>"
        )
        
        # Ensure the log scrolls to the bottom
        self.monitor_log.ensureCursorVisible()
        self.monitor_log.moveCursor(self.monitor_log.textCursor().End)

    def update_monitor_stats(self):
        if not hasattr(self, 'file_events'):
            return
            
        events = ['Created', 'Modified', 'Deleted', 'Moved']
        counts = [self.file_events[e.lower()] for e in events]
        colors = ['#A6E3A1', '#F9E2AF', '#F38BA8', '#89B4FA']

        self.file_events_graph.clear()
        
        # Create bar graph
        bg = pg.BarGraphItem(
            x=range(len(events)), 
            height=counts, 
            width=0.6, 
            brushes=colors
        )
        self.file_events_graph.addItem(bg)
        
        # Set x-axis labels
        axis = self.file_events_graph.getAxis('bottom')
        axis.setTicks([[(i, events[i]) for i in range(len(events))]])
        
        # Set y-axis range to show all data
        max_count = max(counts) if counts else 1
        self.file_events_graph.setYRange(0, max_count + 1)

    def recover_deleted_files(self):
        recovery_folder = QFileDialog.getExistingDirectory(self, "Select Recovery Folder")
        if not recovery_folder:
            self.output_text.append("⚠️ Recovery canceled!\n")
            return

        self.output_text.append("🔄 File recovery not implemented in this version.\n")

    def optimize_storage(self):
        self.output_text.append("🛠️ Optimizing storage...\n")
        
        try:
            # 1. Clean temporary files
            temp_dirs = []
            if os.name == 'nt':  # Windows
                temp_dirs = [
                    os.path.join(os.environ['TEMP']),
                    os.path.join(os.environ['WINDIR'], 'Temp'),
                    os.path.join(os.environ['LOCALAPPDATA'], 'Temp')
                ]
            else:  # Linux/Mac
                temp_dirs = ['/tmp', '/var/tmp', os.path.expanduser('~/tmp')]
                
            temp_files_cleaned = 0
            temp_size = 0
            for temp_dir in temp_dirs:
                if os.path.exists(temp_dir):
                    for filename in os.listdir(temp_dir):
                        file_path = os.path.join(temp_dir, filename)
                        try:
                            if os.path.isfile(file_path):
                                file_size = os.path.getsize(file_path)
                                os.remove(file_path)
                                temp_files_cleaned += 1
                                temp_size += file_size
                        except Exception as e:
                            continue
            
            # 2. Find and suggest large files for cleanup
            large_files = []
            if self.scanned_files:
                large_files = sorted(
                    [f for f in self.scanned_files if f['size_mb'] > 100],
                    key=lambda x: x['size_mb'],
                    reverse=True
                )[:10]
            
            # 3. Clear cache directories
            cache_dirs = []
            if os.name == 'nt':  # Windows
                cache_dirs = [
                    os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'Windows', 'INetCache'),
                    os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'Windows', 'INetCookies')
                ]
            else:  # Linux/Mac
                cache_dirs = [
                    os.path.expanduser('~/.cache'),
                    os.path.expanduser('~/Library/Caches')  # Mac
                ]
                
            cache_files_cleaned = 0
            cache_size = 0
            for cache_dir in cache_dirs:
                if os.path.exists(cache_dir):
                    for root, _, files in os.walk(cache_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            try:
                                file_size = os.path.getsize(file_path)
                                os.remove(file_path)
                                cache_files_cleaned += 1
                                cache_size += file_size
                            except Exception:
                                continue
            
            # 4. Find duplicate files (basic implementation)
            duplicates = {}
            if self.scanned_files:
                for file in self.scanned_files:
                    try:
                        file_hash = hash((file['name'], file['size_mb']))
                        if file_hash in duplicates:
                            duplicates[file_hash].append(file)
                        else:
                            duplicates[file_hash] = [file]
                    except:
                        continue
            
            real_duplicates = [files for files in duplicates.values() if len(files) > 1]
            
            # Display results
            self.output_text.append(f"✅ Optimization results:\n")
            self.output_text.append(f"🗑️ Cleaned {temp_files_cleaned} temp files ({(temp_size/(1024*1024)):.2f} MB)\n")
            self.output_text.append(f"🗑️ Cleaned {cache_files_cleaned} cache files ({(cache_size/(1024*1024)):.2f} MB)\n")
            
            if large_files:
                self.output_text.append("\n⚠️ Large files (>100MB) found (consider cleaning):\n")
                for file in large_files:
                    self.output_text.append(f"📦 {file['path']} - {file['size_mb']:.2f} MB\n")
            
            if real_duplicates:
                self.output_text.append("\n⚠️ Potential duplicate files found:\n")
                for dup_group in real_duplicates[:5]:  # Show first 5 groups
                    self.output_text.append(f"🔁 Files with same name/size ({len(dup_group)} copies):\n")
                    for file in dup_group[:3]:  # Show first 3 of each group
                        self.output_text.append(f"   - {file['path']}\n")
                    if len(dup_group) > 3:
                        self.output_text.append(f"   ... and {len(dup_group)-3} more\n")
            
            self.output_text.append("\n💡 Tip: Review the suggested files before deleting them permanently.\n")
            
        except Exception as e:
            self.output_text.append(f"❌ Optimization failed: {str(e)}\n")

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Monitor")
        if folder:
            self.folder_to_monitor = folder
            self.output_text.append(f"📂 Selected Folder for Monitoring: {folder}\n")
            self.monitoring_folder_label.setText(f"Selected folder: {folder}")
            self.start_monitor_btn.setEnabled(True)

    def clear_output(self):
        self.output_text.clear()
        self.output_text.append("🗑️ Log cleared!\n")

    def update_system_info(self):
        cpu_usage = psutil.cpu_percent()
        self.cpu_usage_label.setText(f"💻 CPU Usage: {cpu_usage}%")
        self.cpu_data.append(cpu_usage)

        memory_usage = psutil.virtual_memory().percent
        self.memory_usage_label.setText(f"🧠 Memory Usage: {memory_usage}%")
        self.memory_data.append(memory_usage)

        self.time_data.append(len(self.time_data))

        self.cpu_curve.setData(self.time_data, self.cpu_data)
        self.memory_curve.setData(self.time_data, self.memory_data)

        if len(self.time_data) > 60:
            self.cpu_data.pop(0)
            self.memory_data.pop(0)
            self.time_data.pop(0)

    def closeEvent(self, event):
        if hasattr(self, 'observer') and self.observer:
            self.observer.stop()
            self.observer.join()
        if hasattr(self, 'scanner_thread') and self.scanner_thread and self.scanner_thread.isRunning():
            self.scanner_thread.quit()
        if hasattr(self, 'system_info_timer'):
            self.system_info_timer.stop()
        if hasattr(self, 'monitor_timer'):
            self.monitor_timer.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FileSystemTool()
    window.show()
    sys.exit(app.exec_())