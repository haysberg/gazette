package main

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
)

var db *gorm.DB

func main() {
	db, err := gorm.Open(sqlite.Open("file::memory:?cache=shared"), &gorm.Config{})
	if err != nil {
		panic("failed to connect database")
	}
	// Migrate the schema
	db.AutoMigrate(&Feed{})
	setupFeeds()

	r := gin.Default()
	r.StaticFS("/", http.Dir("static"))
	// Listen and Server in 0.0.0.0:8080
	r.Run(":8080")
}
